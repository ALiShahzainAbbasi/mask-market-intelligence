from pathlib import Path

import pytest
from mask_api.research_runner.configuration import (
    ConfigurationError,
    LoadedConfiguration,
    load_formula_configuration,
    load_market_configuration,
    load_source_profile,
)
from mask_api.research_runner.contracts import MarketConfiguration, MethodId
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[4]


def test_approved_configs_load_and_have_stable_sha256() -> None:
    formula = load_formula_configuration(ROOT / "configs/formulas/v1.yaml")
    market = load_market_configuration(ROOT / "configs/markets/us_hvac_10_99.yaml")
    sources = load_source_profile(ROOT / "configs/sources/default_us_public.yaml")

    assert formula.value.formula_version == "v1"
    assert set(formula.value.method_formulas) == set(MethodId)
    assert market.value.formula_version == formula.value.formula_version
    assert market.value.source_policy_profile == sources.value.profile_id
    assert all(len(item.sha256) == 64 for item in (formula, market, sources))


def test_v1_weights_and_unknown_boundaries_match_approved_contract() -> None:
    value = load_formula_configuration(ROOT / "configs/formulas/v1.yaml").value

    assert sum(value.overall_weights.values()) == 1
    assert value.method_formulas[MethodId.M2].sample is not None
    assert value.method_formulas[MethodId.M2].sample.unknown_below == 100
    assert value.method_formulas[MethodId.M8].sample is not None
    assert value.method_formulas[MethodId.M8].sample.unknown_below == 10
    assert value.method_formulas[MethodId.M10].sample is not None
    assert value.method_formulas[MethodId.M10].sample.full_target_any_of == {
        "qualified_leads": 30,
        "qualified_opportunities": 10,
    }


def test_network_sources_are_opt_in_and_routes_are_resolved() -> None:
    profile = load_source_profile(ROOT / "configs/sources/default_us_public.yaml").value

    assert profile.sources
    assert all(not source.default_enabled for source in profile.sources.values())
    assert profile.sources["rss_atom"].operational_status == "available"
    assert profile.sources["static_html"].operational_status == "available"
    assert profile.sources["google_places"].operational_status == "paid_hold"
    assert profile.sources["youtube"].operational_status == "available"
    assert profile.sources["reddit"].operational_status == "approval_pending"
    known = set(profile.sources)
    for route in profile.signal_routes.values():
        assert set((*route.primary, *route.fallback)) <= known


def test_hash_uses_validated_content_not_yaml_key_order(tmp_path: Path) -> None:
    first = tmp_path / "first.yaml"
    second = tmp_path / "second.yaml"
    first.write_text(
        """market_id: test_market
name: Test Market
geography: {country: US}
industry_codes: {naics: [541511]}
company_band: {employees_min: 1, employees_max: 9}
buyer_titles: [Owner]
seed_terms: [test term]
seed_problems: [test problem]
research_window_days: 30
language: en-US
source_policy_profile: default_us_public
formula_version: v1
""",
        encoding="utf-8",
    )
    second.write_text(
        """formula_version: v1
source_policy_profile: default_us_public
language: en-US
research_window_days: 30
seed_problems: [test problem]
seed_terms: [test term]
buyer_titles: [Owner]
company_band: {employees_max: 9, employees_min: 1}
industry_codes: {naics: [541511]}
geography: {country: US}
name: Test Market
market_id: test_market
""",
        encoding="utf-8",
    )

    assert load_market_configuration(first).sha256 == load_market_configuration(second).sha256


@pytest.mark.parametrize(
    "yaml_text",
    [
        """market_id: invalid
name: Invalid
geography: {country: USA}
industry_codes: {naics: [541511]}
company_band: {employees_min: 10, employees_max: 9}
buyer_titles: [Owner]
seed_terms: [term]
seed_problems: [problem]
research_window_days: 30
language: en-US
source_policy_profile: default_us_public
formula_version: v1
""",
        """market_id: invalid
name: Invalid
geography: {country: US}
industry_codes: {naics: [541511, 541511]}
company_band: {employees_min: 1, employees_max: 9}
buyer_titles: [Owner]
seed_terms: [term]
seed_problems: [problem]
research_window_days: 30
language: en-US
source_policy_profile: default_us_public
formula_version: v1
unexpected: forbidden
""",
        """market_id: invalid
name: Invalid
geography: {country: US}
industry_codes: {naics: [541511]}
company_band: {employees_min: 1, employees_max: 9}
buyer_titles: [Owner]
seed_terms: [term]
seed_problems: [problem]
research_window_days: 30
language: en-US
validation: {enabled: true, max_budget_usd: 0}
source_policy_profile: default_us_public
formula_version: v1
""",
    ],
)
def test_invalid_market_configuration_is_rejected(tmp_path: Path, yaml_text: str) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text(yaml_text, encoding="utf-8")

    with pytest.raises(ConfigurationError, match="Configuration validation failed"):
        load_market_configuration(path)


def test_configuration_errors_do_not_echo_file_contents(tmp_path: Path) -> None:
    marker = "sensitive-marker-that-must-not-be-echoed"
    path = tmp_path / "invalid.yaml"
    path.write_text(f"secret: {marker}\n", encoding="utf-8")

    with pytest.raises(ConfigurationError) as captured:
        load_market_configuration(path)

    assert marker not in str(captured.value)


def test_loader_returns_typed_immutable_contract() -> None:
    loaded: LoadedConfiguration[MarketConfiguration] = load_market_configuration(
        ROOT / "configs/markets/us_hvac_10_99.yaml"
    )
    with pytest.raises(ValidationError):
        loaded.value.name = "changed"
