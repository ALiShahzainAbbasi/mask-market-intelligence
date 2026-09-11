"""The first real MethodExecutor: M1 from live Census County Business Patterns data.

This module owns no source-fetching or scoring logic of its own. It wires
`mask_api.modules.official_data` (the source) into
`mask_api.modules.method_metrics.calculate_m1` (the scoring) through the
public port each module already exposes -- exactly the "runner coordinates
public module ports" boundary `docs/MODULARITY.md` describes for
`research_runner/`. All five M1 components come from the same Census CBP
dataset so `require_shared_geography`/`require_shared_population` hold
without approximation:

- serviceable_businesses: real establishment count in the company band.
- target_band_share: that count divided by all establishments in the NAICS.
- annual_payroll_per_serviceable_establishment_usd: real aggregate payroll
  in the band divided by establishments in the band.
- fragmentation_share: share of total industry employment held by
  establishments with under 100 employees (a standard fragmentation
  proxy -- not concentration among a few large players).
- growth_cagr: the band's real establishment-count CAGR between a current
  and a five-years-earlier Census CBP release, at the same NAICS/band
  definition -- not a different, broader BLS series, which would violate
  the shared-population check `calculate_m1` enforces (and should).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal

from pydantic import SecretStr

from mask_api.modules.method_metrics import (
    M1Inputs,
    MetricProvenance,
    ObservationState,
    SourcedMetric,
    calculate_m1,
)
from mask_api.modules.official_data import census_cbp_request
from mask_api.modules.official_data.transport import (
    OfficialApiAdapter,
    OfficialApiSettings,
    OfficialTransport,
    OfficialTransportError,
    UrllibOfficialTransport,
)
from mask_api.research_runner.artifacts import ArtifactKind
from mask_api.research_runner.contracts import MethodId
from mask_api.research_runner.execution import (
    MethodExecutionContext,
    MethodExecutionResult,
    MethodRunStatus,
)

CENSUS_API_KEY_ENV = "MASK_CENSUS_API_KEY"
_CONTACT_USER_AGENT = "MASK-AI-Market-Research/0.1"
_CURRENT_YEAR = 2022
_COMPARISON_YEAR = 2017
_ALL_ESTABLISHMENTS_CODE = "001"

# Census CBP employment-size class codes, stable across CBP vintages.
# (code, low_employees, high_employees)
_EMPSZES_BANDS: tuple[tuple[str, int, int], ...] = (
    ("210", 1, 4),
    ("220", 5, 9),
    ("230", 10, 19),
    ("241", 20, 49),
    ("242", 50, 99),
    ("251", 100, 249),
    ("252", 250, 499),
    ("254", 500, 999),
    ("260", 1000, 10_000_000),
)
_SMALL_EMPLOYER_CODES = tuple(code for code, _low, high in _EMPSZES_BANDS if high < 100)


@dataclass(frozen=True)
class _BandObservation:
    establishments: Decimal
    employment: Decimal
    payroll_usd: Decimal


_ZERO_BAND = _BandObservation(Decimal(0), Decimal(0), Decimal(0))


class CensusM1Executor:
    method_id = MethodId.M1
    version = "census-cbp-m1-v1"

    def __init__(self, transport: OfficialTransport | None = None) -> None:
        self._transport = transport or UrllibOfficialTransport()

    def execute(self, context: MethodExecutionContext) -> MethodExecutionResult:
        api_key = os.environ.get(CENSUS_API_KEY_ENV)
        if not api_key:
            return MethodExecutionResult(
                status=MethodRunStatus.UNKNOWN, reason_code="m1.census_api_key_missing"
            )

        market = context.market.value
        naics = market.industry_codes.naics[0]
        band_min = market.company_band.employees_min
        band_max = market.company_band.employees_max
        target_codes = tuple(
            code for code, low, high in _EMPSZES_BANDS if low >= band_min and high <= band_max
        )
        if not target_codes:
            return MethodExecutionResult(
                status=MethodRunStatus.UNKNOWN,
                reason_code="m1.no_census_band_covers_company_band",
            )

        source = context.sources.value.sources.get("census_cbp")
        if source is None:
            return MethodExecutionResult(
                status=MethodRunStatus.UNKNOWN,
                reason_code="m1.census_cbp_source_not_registered",
            )
        adapter = OfficialApiAdapter(
            "census_cbp",
            source.model_copy(update={"operational_status": "available"}),
            OfficialApiSettings(enabled=True, policy_approved=True),
            self._transport,
            user_agent=_CONTACT_USER_AGENT,
        )
        secret_key = SecretStr(api_key)

        try:
            current_codes = tuple({*target_codes, _ALL_ESTABLISHMENTS_CODE, *_SMALL_EMPLOYER_CODES})
            current, current_requests = self._fetch_year(
                adapter, context, naics, current_codes, _CURRENT_YEAR, secret_key
            )
            comparison, comparison_requests = self._fetch_year(
                adapter, context, naics, target_codes, _COMPARISON_YEAR, secret_key
            )
        except OfficialTransportError as error:
            return MethodExecutionResult(
                status=MethodRunStatus.FAILED, reason_code=f"m1.{error.code}"
            )

        inputs = self._build_inputs(
            market.market_id, naics, band_min, band_max, target_codes, current, comparison
        )
        formula = context.formula.value.method_formulas[MethodId.M1]
        result = calculate_m1(
            formula_version=context.formula.value.formula_version,
            formula=formula,
            inputs=inputs,
        )

        self._persist_raw(context, current_requests + comparison_requests)

        return MethodExecutionResult(
            status=MethodRunStatus.SUCCEEDED,
            reason_code=f"m1.{result.status.value}",
            payload=result.model_dump(mode="json"),
        )

    def _fetch_year(
        self,
        adapter: OfficialApiAdapter,
        context: MethodExecutionContext,
        naics: int,
        codes: tuple[str, ...],
        year: int,
        api_key: SecretStr,
    ) -> tuple[dict[str, _BandObservation], list[tuple[int, str, bytes]]]:
        by_code: dict[str, _BandObservation] = {}
        raw: list[tuple[int, str, bytes]] = []
        for code in codes:
            request = census_cbp_request(
                year=year, naics=naics, employment_size=code, geography="us:*", api_key=api_key
            )
            fetch_result = adapter.fetch(request, context.budget)
            observations = {obs.metric: obs.value for obs in fetch_result.batch.observations}
            by_code[code] = _BandObservation(
                establishments=observations.get("establishment_count", Decimal(0)),
                employment=observations.get("employment", Decimal(0)),
                payroll_usd=observations.get("annual_payroll_usd", Decimal(0)),
            )
            raw.append((year, code, fetch_result.batch.raw_response))
        return by_code, raw

    def _build_inputs(
        self,
        market_id: str,
        naics: int,
        band_min: int,
        band_max: int,
        target_codes: tuple[str, ...],
        current: dict[str, _BandObservation],
        comparison: dict[str, _BandObservation],
    ) -> M1Inputs:
        geography = "US"
        population = f"NAICS {naics} establishments, {band_min}-{band_max} employees"
        period = str(_CURRENT_YEAR)

        def metric(
            value: Decimal, unit: str, evidence_ref: str, period_value: str = period
        ) -> SourcedMetric:
            return SourcedMetric(
                value=value,
                provenance=MetricProvenance(
                    source_id="census_cbp",
                    evidence_reference=evidence_ref,
                    observation_state=ObservationState.OBSERVED,
                    geography=geography,
                    population=population,
                    period=period_value,
                    unit=unit,
                ),
            )

        def sum_band(
            bands: dict[str, _BandObservation], codes: tuple[str, ...]
        ) -> _BandObservation:
            return _BandObservation(
                establishments=sum(
                    (bands.get(c, _ZERO_BAND).establishments for c in codes), Decimal(0)
                ),
                employment=sum((bands.get(c, _ZERO_BAND).employment for c in codes), Decimal(0)),
                payroll_usd=sum((bands.get(c, _ZERO_BAND).payroll_usd for c in codes), Decimal(0)),
            )

        target = sum_band(current, target_codes)
        all_establishments = current.get(_ALL_ESTABLISHMENTS_CODE, _ZERO_BAND)
        band_codes = "+".join(target_codes)

        serviceable_businesses = metric(
            target.establishments,
            "establishments",
            f"census_cbp:{_CURRENT_YEAR}:NAICS{naics}:EMPSZES={band_codes}:ESTAB",
        )

        target_band_share = (
            metric(
                target.establishments / all_establishments.establishments,
                "share",
                f"census_cbp:{_CURRENT_YEAR}:NAICS{naics}:EMPSZES={band_codes}_over_001:ESTAB_share",
            )
            if all_establishments.establishments
            else None
        )

        economic_capacity = (
            metric(
                target.payroll_usd / target.establishments,
                "USD",
                f"census_cbp:{_CURRENT_YEAR}:NAICS{naics}:EMPSZES={band_codes}:PAYANN_per_ESTAB",
            )
            if target.establishments
            else None
        )

        small = sum_band(current, _SMALL_EMPLOYER_CODES)
        fragmentation_share = (
            metric(
                small.employment / all_establishments.employment,
                "share",
                f"census_cbp:{_CURRENT_YEAR}:NAICS{naics}:employment_under_100_employees_share",
            )
            if all_establishments.employment
            else None
        )

        comparison_target = sum_band(comparison, target_codes)
        growth_cagr = None
        if comparison_target.establishments and target.establishments:
            years = Decimal(_CURRENT_YEAR - _COMPARISON_YEAR)
            ratio = target.establishments / comparison_target.establishments
            growth_cagr = metric(
                ratio ** (Decimal(1) / years) - 1,
                "cagr",
                (
                    f"census_cbp:{_COMPARISON_YEAR}->{_CURRENT_YEAR}:NAICS{naics}:"
                    f"EMPSZES={band_codes}:ESTAB_cagr"
                ),
                period_value=f"{_COMPARISON_YEAR}-{_CURRENT_YEAR}",
            )

        return M1Inputs(
            market_id=market_id,
            serviceable_businesses=serviceable_businesses,
            growth_cagr=growth_cagr,
            fragmentation_share=fragmentation_share,
            annual_payroll_per_serviceable_establishment_usd=economic_capacity,
            target_band_share=target_band_share,
        )

    def _persist_raw(
        self, context: MethodExecutionContext, raw: list[tuple[int, str, bytes]]
    ) -> None:
        for year, code, body in raw:
            path = f"official_data/census_cbp/{year}_{code}.json"
            context.artifacts.write_bytes(ArtifactKind.RAW, path, body)
