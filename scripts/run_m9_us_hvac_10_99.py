"""Run real M9 (MASK AI & productization fit) for us_hvac_10_99 from the
owner-supplied capability registry (MASK_AI_Capability_Registry_and_Fit_
Framework.docx, v1.0, Sept 2026) plus this market's real M2/M3 evidence.

Not a MethodExecutor yet (M9 has none registered) -- a one-off driver,
matching scripts/run_census_m1.py's proof-of-real-wiring pattern.

Per docs/AUTONOMOUS_RESEARCH_MODE.md and the registry document's own
section 10 ("How Claude Must Use This Registry for M9"), technical_fit
and integration_fit map directly and mechanically onto the registry's
CAP-IDs and evidence levels -- PROVEN/DEMONSTRATED count as coverage,
ADJACENT/LIMITED do not. Those two components are the least subjective
in this script.

The other five components (standardization, recurring_revenue_potential,
proof_potential, delivery_simplicity, expansion_potential) are, per the
registry's own text, real judgment calls informed by the registry's
stated criteria and this market's real evidence -- not something the
registry states as a fixed number. Every one of those judgment calls is
commented inline with the exact real fact it is grounded in, and this
script's result should be reviewed by the owner (the registry's own
"leadership/technical reviewer") before being treated as final, not
silently accepted as an AI-decided score.

Real capability requirements were deliberately drawn only from the
subset of this market's real M2 pain evidence that is actually
automation/integration-addressable. Several other real pain mentions
(SBA/financing conditions, physical equipment engineering, technician
skill/training gaps, general lead generation) are NOT included as
requirements: they are real market pain, but not something this
registry claims a core MASK AI capability for, and stretching the
mapping to cover them would violate the registry's own "earned by
evidence, not by saying we can build it" rule.

Usage:
    uv run python scripts/run_m9_us_hvac_10_99.py
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api/src"))

from mask_api.modules.method_metrics import (  # noqa: E402
    CapabilityCoverage,
    CapabilityRequirement,
    IntegrationRecord,
    M9Inputs,
    MetricProvenance,
    ObservationState,
    SourcedMetric,
    calculate_m9,
)
from mask_api.research_runner.configuration import load_formula_configuration  # noqa: E402
from mask_api.research_runner.contracts import MethodId  # noqa: E402

MARKET_ID = "us_hvac_10_99"
REGISTRY_REF = "MASK AI Capability Registry & Delivery Fit Framework v1.0, Sept 2026"
_RUN_TIMESTAMP = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
RUN_DIR = ROOT / "outputs" / "runs" / f"m9_us_hvac_10_99_{_RUN_TIMESTAMP}"


def main() -> None:
    # --- technical_fit: real capability requirements, drawn only from the
    # automation/integration-addressable subset of real M2 pain evidence,
    # weighted by the registry's own stated capability-hierarchy priority
    # order (section 1: Automation > Integration > Conversational > ... ).
    requirements = (
        CapabilityRequirement(
            capability_id="workflow_automation",
            description=(
                "Automate dispatch/scheduling/intake workflow chaos -- the core "
                "real pain of running a scheduling/dispatch-dependent business "
                "(this market's own NAICS-238220 definition)."
            ),
            required_weight=Decimal("0.30"),
            evidence_reference=(
                "Real M2 evidence, 9 mentions extracted 2026-09-14 (see AUTONOMOUS-039): "
                "pain_category 'Operations'/'Administrative and Operational Burden' themes "
                "(e.g. mention f8744..., 'difficulty managing the maintenance-agreement list')."
            ),
        ),
        CapabilityRequirement(
            capability_id="system_integration",
            description=(
                "Connect to the scheduling/CRM system(s) this market's real businesses "
                "already run on, rather than replacing them."
            ),
            required_weight=Decimal("0.25"),
            evidence_reference=(
                "Real M2 mention f87442f8...: 'we use jobber now and thats the challenge' "
                "-- a real, named, currently-used system (see also AUTONOMOUS-043's M5 result)."
            ),
        ),
        CapabilityRequirement(
            capability_id="voice_telephony",
            description="Handle missed/after-hours inbound calls without losing the lead.",
            required_weight=Decimal("0.20"),
            evidence_reference=(
                "Real M2 mention a78c6620...: 'a lot of revenue gets lost after the call if "
                "nobody follows up' (severity 7, economic_impact 7, real source video titled "
                "\"This AI Agent Recovers HVAC Companies $140K+ In Missed Calls\")."
            ),
        ),
        CapabilityRequirement(
            capability_id="crm_revenue_ops",
            description="Follow-up, appointment confirmation, and lead re-engagement.",
            required_weight=Decimal("0.15"),
            evidence_reference=(
                "Same real M2 mention a78c6620... (Revenue Loss / Follow-up and Lead "
                "Re-engagement, purchase_intent_0_4=2)."
            ),
        ),
        CapabilityRequirement(
            capability_id="field_service_ops",
            description="Technician dispatch/scheduling workflow specific to field service.",
            required_weight=Decimal("0.10"),
            evidence_reference=(
                "Market definition itself (NAICS 238220 field-service dispatch business) "
                "plus real M2 scheduling/dispatch pain themes."
            ),
        ),
    )
    coverage = (
        CapabilityCoverage(
            capability_id="workflow_automation",
            covered=True,
            evidence_reference=f"{REGISTRY_REF}, CAP-01 (PROVEN): Expert Buddy, Google Reviews "
            "automation, CRM/workflow automation, internal market-intelligence pipelines.",
            source_id="mask_ai_capability_registry",
        ),
        CapabilityCoverage(
            capability_id="system_integration",
            covered=True,
            evidence_reference=f"{REGISTRY_REF}, CAP-02 (PROVEN): Expert Buddy, Mr Props, SEC "
            "filings, Google Reviews automation, internal market-intelligence engine.",
            source_id="mask_ai_capability_registry",
        ),
        CapabilityCoverage(
            capability_id="voice_telephony",
            covered=True,
            evidence_reference=f"{REGISTRY_REF}, CAP-04 (DEMONSTRATED): AI Voice Agent build "
            "experience; HydroHelp911 active delivery.",
            source_id="mask_ai_capability_registry",
        ),
        CapabilityCoverage(
            capability_id="crm_revenue_ops",
            covered=True,
            evidence_reference=f"{REGISTRY_REF}, CAP-07 (DEMONSTRATED): CRM/workflow automation; "
            "HydroHelp911; voice-agent work.",
            source_id="mask_ai_capability_registry",
        ),
        CapabilityCoverage(
            capability_id="field_service_ops",
            covered=True,
            evidence_reference=f"{REGISTRY_REF}, CAP-08 (DEMONSTRATED): HydroHelp911 -- home-"
            "services voice automation, after-hours intake, dispatch/scheduling handoff -- a "
            "direct real analog to this market's own dispatch workflow.",
            source_id="mask_ai_capability_registry",
        ),
    )

    # --- integration_fit: the one real, specifically-named system this
    # market's real evidence shows in active use (Jobber). Prevalence is
    # deliberately conservative: only 1 of 9 real M2 mentions named a
    # currently-used tool by name, though a separate real YouTube search
    # ("HVAC dispatch software") independently surfaced Jobber as one of
    # three tools in a real comparison-video title, so it is not an
    # isolated data point -- still, this is a thin, directional estimate,
    # not a market-share statistic, and is labeled as such.
    integrations = (
        IntegrationRecord(
            platform_id="jobber",
            platform_name="Jobber",
            target_market_prevalence_0_1=Decimal("0.30"),
            supported=True,
            evidence_reference=(
                "THIN ESTIMATE: 1 of 9 real M2 mentions named Jobber as currently used "
                "(mention f87442f8...); corroborated by a real YouTube video comparing "
                "Jobber vs Housecall Pro vs FieldEdge (AUTONOMOUS-045). supported=True "
                "reflects comparable REST/webhook integration experience (Builder Prime, "
                "registry CAP-02 + HydroHelp911), not a prior literal Jobber integration."
            ),
            source_id="mask_ai_capability_registry",
        ),
    )

    def metric(value: Decimal, unit: str, note: str) -> SourcedMetric:
        return SourcedMetric(
            value=value,
            provenance=MetricProvenance(
                source_id="mask_ai_capability_registry",
                evidence_reference=note,
                observation_state=ObservationState.ESTIMATED,
                geography="US",
                population="us_hvac_10_99 market fit assessment",
                period="2026-09",
                unit=unit,
            ),
        )

    inputs = M9Inputs(
        market_id=MARKET_ID,
        capability_requirements=requirements,
        capability_coverage=coverage,
        integrations=integrations,
        # standardization: real, multi-vendor SaaS category (Jobber, Housecall
        # Pro, FieldEdge all independently found via real search) serving this
        # exact workflow is strong evidence the workflow itself is standardized
        # across firms -- 0.70 reflects "high but not uniform" (businesses still
        # differ in which specific tool/process they use).
        workflow_template_similarity_0_1=metric(
            Decimal("0.70"),
            "similarity_0_1",
            "JUDGMENT CALL: real multi-vendor category (Jobber/Housecall Pro/FieldEdge, "
            "real YouTube comparison video) as standardization evidence -- not a precise "
            "measurement. Owner review requested.",
        ),
        # recurring_revenue_potential: the registry's own stated preferred
        # pattern (section 7) is ~70-80% reusable logic for exactly this
        # service shape (voice/dispatch automation); 0.75 is the midpoint of
        # that owner-documented range, not a new number.
        recurring_solution_value_share=metric(
            Decimal("0.75"),
            "share",
            f"{REGISTRY_REF} §7: 'Strong recurring fit' category (voice/WhatsApp "
            "agents, managed automations) states ~70-80% reusable logic; midpoint used.",
        ),
        # proof_potential: conservative count of DIRECTLY comparable (not just
        # same-CAP-family) real delivered projects -- HydroHelp911 (field-
        # service/dispatch/voice, closest real analog) and the CRM & workflow
        # automation engagements line (same core automation+integration
        # pattern). Expert Buddy/Google Reviews were excluded as less directly
        # comparable to a dispatch/field-service workflow specifically.
        comparable_internal_project_count=metric(
            Decimal("2"),
            "projects",
            f"{REGISTRY_REF} §4: HydroHelp911 (home-services dispatch/voice, DELIVERED) "
            "+ CRM & workflow automation engagements (DELIVERED/REPEATABLE). Conservative "
            "count -- other CAP-01/02 projects (Expert Buddy, Google Reviews) not counted "
            "as directly comparable to a field-service dispatch workflow.",
        ),
        # delivery_complexity_index_0_10 (0=trivial, 10=extremely complex):
        # moderate-low -- HydroHelp911 is a direct, already-delivered real
        # precedent (not novel), the registry names no HIPAA/PCI/regulated
        # burden for this domain, and Jobber-class tools are typical
        # documented SaaS REST APIs, not proprietary/legacy integration.
        delivery_complexity_index_0_10=metric(
            Decimal("3.0"),
            "complexity_0_10",
            "JUDGMENT CALL: moderate-low, based on HydroHelp911 direct precedent and no "
            "regulated-industry burden noted for this domain in the registry. Owner review "
            "requested.",
        ),
        # expansion_potential: real adjacent workflows grounded in OTHER real
        # M2 pain themes that also map to a PROVEN/DEMONSTRATED capability --
        # (1) the after-hours/missed-call wedge itself, (2) CRM/follow-up
        # automation, (3) administrative/document processing (real mention:
        # paperwork/supplier search -> CAP-06/11 Document AI, PROVEN). Kept to
        # 3, not counting real pains this registry does NOT claim strength in
        # (financing/M&A, physical equipment engineering, technician training).
        adjacent_high_value_workflow_count=metric(
            Decimal("3"),
            "workflows",
            "JUDGMENT CALL: (1) after-hours/missed-call intake+dispatch wedge, (2) CRM/"
            "follow-up automation, (3) administrative/document processing (real M2 mention: "
            "paperwork/supplier search -> CAP-06/11, PROVEN). Deliberately excludes real "
            "pain themes outside this registry's claimed strengths (financing/M&A, physical "
            "equipment engineering, technician skill/training).",
        ),
    )

    formulas = load_formula_configuration(ROOT / "configs/formulas/v1.yaml").value
    m9_formula = formulas.method_formulas[MethodId.M9]
    result = calculate_m9(
        formula_version=formulas.formula_version, formula=m9_formula, inputs=inputs
    )

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    (RUN_DIR / "m9_result.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")

    print(f"status={result.status.value} score={result.score}")
    print(f"unknown_reasons={list(result.unknown_reasons)}")
    for item in result.breakdown:
        print(
            f"  {item.component}: status={item.status.value} "
            f"raw_value={item.raw_value} score={item.transformed_score}"
        )
    print(f"Output: {RUN_DIR}")


if __name__ == "__main__":
    main()
