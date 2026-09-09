# M3 Workflow Intelligence

Status: A13 offline implementation.

`mask_api.modules.workflow_intelligence` implements the zero-paid-cost M3
processing path after A10 grounding. It does not collect sources or invoke an
LLM. It accepts only `GroundingReport` values that are accepted and explicitly
expose `scoring_input` validated against the new `workflow-step-v1` analysis
schema (`mask_api.modules.analysis.schemas.WorkflowStepOutput`).

## Pipeline

```text
A10-accepted workflow-step-v1 output
  -> lineage-rich workflow-step evidence
  -> exact grouping by normalized step-name hash (no semantic clustering)
  -> per-step component means and formulas/v1.yaml transforms
  -> max + sqrt(evidence-count)-weighted top-five M3 aggregation
  -> lineage-rich report contract
```

Unlike M2's free-text pain mentions, a workflow step has a natural identity —
what the analyst or model named it — so steps are grouped by an exact
normalized-name hash rather than embeddings/clustering. Evidence describing
the same step is averaged, not summed: duplicate or repeated evidence cannot
inflate a step's volume, labor burden, or any other component, and a step's
`evidence_count` (the sqrt-weight used in market aggregation) only grows when
a genuinely distinct evidence record is added. Exact duplicate evidence
(same `evidence_id`, derived from market/document/analysis-cache/step-name) is
rejected rather than silently deduplicated.

## Formula and honest status

The calculator consumes the validated M3 `MethodFormula` loaded from
`configs/formulas/v1.yaml`; it does not ask a model to score. Per step it uses:

- volume: `events_per_month` mapped logarithmically from 10–10,000 to 0–10;
- labor burden: `labor_hours_per_month` mapped logarithmically from 10–1,000;
- failure rate: mapped linearly from 0.00–0.20;
- business consequence and automation potential: mean verified 0–10 scores,
  used directly; and
- manuality: `manual_share` mapped linearly from 0.20–1.00.

Any unavailable component on any non-empty step makes the whole M3 result
`unknown` — a missing component on one step never quietly excludes that step
from ranking or lets the weighted sum renormalize around it. There is no v1
M3 sample/partial-completeness rule, so a known result is always `complete`,
never `provisional`. The market score is 60% of the maximum eligible step
score plus 40% of the square-root-evidence-weighted mean of the top five,
exactly as configured.

"No unvalidated AI-generated workflow supports a high-confidence score" (per
`RESEARCH_METHODOLOGY.md`) is a confidence-engine (P13) concern, not this
calculator's: v1's M3 completeness rule is purely about component
availability, and this module does not invent an additional blocking gate.

These statuses are calculation completeness, not AI-quality approval. Human
confirmation of the reconstructed workflow map with target operators, a
labelled AI evaluation set for `workflow-step-v1` extraction, persistence, and
production scoring release remain governed by `EVALUATION.md` and later
phases. Local fixtures never count as market evidence.
