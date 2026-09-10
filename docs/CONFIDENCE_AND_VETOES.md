# Confidence, Completeness, and Automatic Veto Detection

Status: A15 offline implementation.

`mask_api.modules.confidence` implements the deterministic parts of
`SCORING.md` sections 6-9 that are actually approved and computable today. It
sits above the method calculators (`method_metrics`, `pain_intelligence`,
`workflow_intelligence`): it consumes their public result contracts and never
computes a method score itself.

## Confidence

`calculate_confidence` takes the five v1 dimensions
(`source_diversity`, `sample_adequacy`, `evidence_quality`, `recency`,
`cross_source_agreement`), each **already normalized to 0-10**, and applies
the exact weighted expression from `configs/formulas/v1.yaml`:

```text
10 * (0.25*SD + 0.25*SA + 0.20*EQ + 0.10*R + 0.20*A)
```

mapping the 0-100 result to `Low` (<50), `Medium` (50-74.999999), or `High`
(≥75). Any missing dimension keeps the whole result `unknown` — never a
partial or renormalized weighting.

**This module does not derive four of the five dimensions.** SCORING.md
section 6 says their normalization rules are "versioned alongside each
method rubric," and none exist in `configs/formulas/v1.yaml` yet — this is
open decision **D04** in `progress.txt`, still pending an owner/reviewer.
Inventing a normalizer here (for example, "count distinct source families
and call it source diversity") would be exactly the kind of unapproved
methodology change `SCORING.md` forbids, so callers must supply these four
dimensions explicitly once D04 is resolved.

`sample_adequacy` is the exception: v1.yaml's `confidence.sample_targets`
gives an exact target per method (matching that method's own
`sample.full_target`), so `sample_adequacy_score()` computes it generically
via `ratio_score`. Only M2, M5, M6, M8, and M10 have an approved target;
every other method's sample adequacy stays `unknown` through this function
until D04 approves more.

## Completeness

`classify_completeness` maps a method's own computed status
(`unknown`/`provisional`/`complete`) to SCORING.md's evidence-completeness
states: `Proven`, `Weak`, `Missing`, or an explicit `Not applicable` override
for a rubric-excused method (for example M8/M10 with validation disabled).
It carries no additional quality/recency/diversity logic — that is
confidence's job, not completeness's ("Completeness is not confidence and
not score").

## Automatic veto detection

`evaluate_automatic_vetoes` implements the three v1 vetoes with a **purely
numeric** trigger:

| Veto | Trigger |
| --- | --- |
| `no_meaningful_budget` | M4 score < 2 with HIGH confidence |
| `no_reachable_economic_buyer` | M7 `buyer_identification` component < 2 with HIGH confidence |
| `highly_bespoke_delivery` | M9 `standardization` < 3 and `delivery_simplicity` < 3 with MEDIUM or HIGH confidence |

The trigger condition alone marks a finding `suspected`; the confidence
label named in that exact trigger text is required for `confirmed`. Every
result also reports the other three v1 vetoes in `not_evaluated`, honestly,
rather than guessing:

- `major_access_or_regulatory_barrier` and `dominant_platform_solves_problem`
  need an explicit human-verified evidence contract ("verified prohibited,"
  "dominant-solution evidence") that does not exist yet.
- `no_qualified_buying_intent` needs M8/M10 data, which is later work
  (A18/A19).

`resolved` and `accepted_exception` are human review-workflow states (P18)
outside this module's automatic-detection scope; this module only ever
produces `suspected` or `confirmed`. Every v1 veto is treated as `critical`
severity, since `configs/formulas/v1.yaml`'s `vetoes` block defines only
vetoes, not a broader warning taxonomy.

## What is deliberately not built yet

- Deriving `source_diversity`/`evidence_quality`/`recency`/
  `cross_source_agreement` from raw evidence (blocked on D04).
- Gate-score calculation and the Gate 1-4 readiness engine (A16).
- The human veto-investigation/resolution workflow and founder-exception
  records (P18).
- Wiring any of this into the CLI `MethodExecutor`/report pipeline (A17).

Fixtures used in tests are not market evidence or an approved confidence
assessment.
