from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from mask_api.modules.official_data.requests import OfficialRequest
from mask_api.modules.official_data.transport import (
    OfficialTransportError,
    OfficialTransportResponse,
)
from mask_api.research_runner.artifacts import ArtifactKind
from mask_api.research_runner.budgets import BudgetLedger, RunBudgetLimits
from mask_api.research_runner.configuration import (
    LoadedConfiguration,
    load_formula_configuration,
    load_market_configuration,
    load_source_profile,
)
from mask_api.research_runner.contracts import (
    CompanyBand,
    FormulaConfiguration,
    MarketConfiguration,
    SourceProfile,
)
from mask_api.research_runner.execution import MethodExecutionContext
from mask_api.research_runner.executors import census_m1
from mask_api.research_runner.executors.census_m1 import CensusM1Executor
from mask_api.research_runner.local_artifacts import LocalArtifactStore

ROOT = Path(__file__).resolve().parents[5]
NOW = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)

# (establishments, employment, payroll_thousands_usd) per Census CBP EMPSZES code.
# Chosen so every M1 component lands inside its transform's [low, high] band
# (none clamps at the floor/ceiling), matching how the real live run behaved.
_FIXTURE: dict[tuple[int, str], tuple[int, int, int]] = {
    (2022, "001"): (3000, 50000, 400000),
    (2022, "210"): (1200, 2000, 8000),
    (2022, "220"): (600, 3500, 12000),
    (2022, "230"): (400, 5000, 15000),
    (2022, "241"): (300, 8000, 15000),
    (2022, "242"): (100, 7000, 10000),
    (2017, "230"): (350, 4500, 13000),
    (2017, "241"): (250, 7000, 13000),
    (2017, "242"): (80, 6000, 8500),
}


def configurations() -> tuple[
    LoadedConfiguration[MarketConfiguration],
    LoadedConfiguration[FormulaConfiguration],
    LoadedConfiguration[SourceProfile],
]:
    return (
        load_market_configuration(ROOT / "configs/markets/us_hvac_10_99.yaml"),
        load_formula_configuration(ROOT / "configs/formulas/v1.yaml"),
        load_source_profile(ROOT / "configs/sources/default_us_public.yaml"),
    )


@dataclass
class FakeCensusTransport:
    fixture: dict[tuple[int, str], tuple[int, int, int]] = field(default_factory=lambda: _FIXTURE)
    calls: list[OfficialRequest] = field(default_factory=list)

    def execute(self, request: OfficialRequest, **_kwargs: object) -> OfficialTransportResponse:
        self.calls.append(request)
        year = int(request.endpoint.rsplit("/", 2)[1])
        code = request.query["EMPSZES"]
        estab, emp, payroll = self.fixture[(year, code)]
        body = json.dumps(
            [
                ["NAME", "NAICS2017", "NAICS2017_LABEL", "EMPSZES", "ESTAB", "EMP", "PAYANN"],
                [
                    "United States",
                    "238220",
                    "HVAC Contractors",
                    code,
                    str(estab),
                    str(emp),
                    str(payroll),
                ],
            ]
        ).encode()
        return OfficialTransportResponse(
            status_code=200, content_type="application/json", body=body
        )


@dataclass
class FailingCensusTransport:
    def execute(self, request: OfficialRequest, **_kwargs: object) -> OfficialTransportResponse:
        raise OfficialTransportError("official.network_error", retryable=True)


def context(
    tmp_path: Path, market: LoadedConfiguration[MarketConfiguration] | None = None
) -> MethodExecutionContext:
    configured_market, formula, sources = configurations()
    return MethodExecutionContext(
        run_id="m1-fixture-run",
        market=market or configured_market,
        formula=formula,
        sources=sources,
        artifacts=LocalArtifactStore(tmp_path / "run"),
        budget=BudgetLedger(
            RunBudgetLimits(
                max_requests=100,
                max_documents=100,
                max_total_bytes=10_000_000,
                max_duration_seconds=600,
                max_paid_cost_usd=Decimal("0"),
            )
        ),
        deadline=NOW + timedelta(minutes=10),
    )


def test_execute_without_api_key_returns_unknown_before_any_network_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(census_m1.CENSUS_API_KEY_ENV, raising=False)
    transport = FakeCensusTransport()

    result = CensusM1Executor(transport).execute(context(tmp_path))

    assert result.status.value == "unknown"
    assert result.reason_code == "m1.census_api_key_missing"
    assert transport.calls == []


def test_execute_produces_a_complete_score_from_all_five_real_components(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(census_m1.CENSUS_API_KEY_ENV, "fixture-not-a-real-key")
    transport = FakeCensusTransport()

    result = CensusM1Executor(transport).execute(context(tmp_path))

    assert result.status.value == "succeeded"
    assert result.reason_code == "m1.complete"
    assert result.payload["status"] == "complete"
    assert Decimal(result.payload["score"]) > 0

    by_component = {item["component"]: item for item in result.payload["breakdown"]}
    # buyer_pool = establishments in bands 230+241+242 for 2022
    assert Decimal(by_component["buyer_pool"]["raw_value"]) == Decimal(400 + 300 + 100)
    assert by_component["buyer_pool"]["evidence_references"] == [
        "census_cbp:2022:NAICS238220:EMPSZES=230+241+242:ESTAB"
    ]
    # target_band_share = target establishments / all establishments (001)
    assert Decimal(by_component["target_band_match"]["raw_value"]) == Decimal(800) / Decimal(3000)
    # economic_capacity = payroll (USD) / establishments across the target bands
    expected_payroll_usd = Decimal((15000 + 15000 + 10000) * 1000)
    assert Decimal(
        by_component["economic_capacity"]["raw_value"]
    ) == expected_payroll_usd / Decimal(800)
    # growth_cagr computed from the same bands across 2017 -> 2022
    comparison_estab = Decimal(350 + 250 + 80)
    current_estab = Decimal(800)
    expected_cagr = (current_estab / comparison_estab) ** (Decimal(1) / Decimal(5)) - 1
    assert Decimal(by_component["growth"]["raw_value"]) == expected_cagr
    assert by_component["growth"]["evidence_references"] == [
        "census_cbp:2017->2022:NAICS238220:EMPSZES=230+241+242:ESTAB_cagr"
    ]

    # every component shares the same geography/population -- proven indirectly:
    # calculate_m1 would have raised ProvenanceCompatibilityError otherwise.
    assert result.payload["unknown_reasons"] == []


def test_execute_fetches_exactly_nine_bands_and_persists_raw_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(census_m1.CENSUS_API_KEY_ENV, "fixture-not-a-real-key")
    transport = FakeCensusTransport()
    ctx = context(tmp_path)

    CensusM1Executor(transport).execute(ctx)

    assert len(transport.calls) == 9  # 6 bands for 2022, 3 target bands for 2017
    assert "fixture-not-a-real-key" not in json.dumps(
        [call.provenance().model_dump(mode="json") for call in transport.calls]
    )
    assert ctx.budget.usage.requests == 9

    raw_artifacts = ctx.artifacts.list_artifacts(ArtifactKind.RAW)
    assert len(raw_artifacts) == 9
    assert any(item.relative_path.endswith("2022_230.json") for item in raw_artifacts)
    assert any(item.relative_path.endswith("2017_242.json") for item in raw_artifacts)


def test_execute_returns_unknown_when_company_band_matches_no_census_class(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(census_m1.CENSUS_API_KEY_ENV, "fixture-not-a-real-key")
    transport = FakeCensusTransport()
    configured_market, formula, sources = configurations()
    odd_band_market = configured_market.value.model_copy(
        update={"company_band": CompanyBand(employees_min=15, employees_max=30)}
    )
    loaded = LoadedConfiguration(
        path=configured_market.path, value=odd_band_market, sha256=configured_market.sha256
    )

    result = CensusM1Executor(transport).execute(context(tmp_path, market=loaded))

    assert result.status.value == "unknown"
    assert result.reason_code == "m1.no_census_band_covers_company_band"
    assert transport.calls == []


def test_execute_maps_a_transport_error_to_a_failed_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(census_m1.CENSUS_API_KEY_ENV, "fixture-not-a-real-key")

    result = CensusM1Executor(FailingCensusTransport()).execute(context(tmp_path))

    assert result.status.value == "failed"
    assert result.reason_code == "m1.official.network_error"
