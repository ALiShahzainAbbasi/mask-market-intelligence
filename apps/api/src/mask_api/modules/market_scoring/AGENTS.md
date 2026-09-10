# Market scoring module rules

Read the root `AGENTS.md`, `progress.txt`, `docs/SCORING.md` sections 1 and
8-10, `docs/AUTONOMOUS_RESEARCH_MODE.md`, and `docs/MODULARITY.md` before
changing this module.

- This is the top of the calculation stack: it composes `confidence`'s
  method-level results and `method_metrics`/`pain_intelligence`/
  `workflow_intelligence`'s method scores into one market's overall score,
  gate readiness, and snapshot. It never recomputes a method score, a
  confidence dimension, or a veto trigger itself.
- `AutomatedResearchScore` is **never** the market's approved/final score.
  It is the raw (not renormalized) sum of available weighted contributions,
  matching SCORING.md's "provisional contribution" language exactly. Do not
  divide by observed weight to make it look complete when methods are
  missing.
- `FinalValidatedScore` is always `not_ready` today because no reviewed-
  score human-approval workflow exists yet (P12). Do not invent an
  automatic "ready" path — SCORING.md requires all ten *reviewed* scores
  approved under a compatible configuration, and "reviewed" is a human
  action this module has no way to observe yet.
- `aggregate_confidence`'s renormalization across a required-method subset
  is **only** approved for confidence, never for a score. Do not reuse this
  renormalization pattern for `AutomatedResearchScore` or a gate score.
- A gate's `unresolved_reasons` combine, in priority order: a confirmed
  critical veto (`blocked`, checked first, regardless of score) → a missing
  required method score (`not_ready`) → confidence below the gate's
  minimum (`not_ready`) → a Gate 4-style `preferred_score` miss
  (`founder_review_required`) → a `minimum_score` miss
  (`does_not_meet_gate`) → otherwise `eligible_to_advance`. Do not reorder
  these without re-reading SCORING.md section 8's exact result taxonomy.
- `GateEvaluation`/`MarketScoreSnapshot` compute *eligibility* only. Never
  assign an actual stage transition (`advance`/`hold`/`reject`/`select`) —
  SCORING.md: "Eligibility never changes a market stage automatically."
- `risk_adjusted_method_score` is a secondary display metric
  (`raw * (0.70 + 0.30 * confidence/100)`). It must never replace, hide, or
  feed back into the raw method score, the automated research score, or any
  gate calculation.
- A snapshot is immutable: a new run always produces a new
  `MarketScoreSnapshot`, never an in-place update. `snapshots_are_comparable`
  is the only approved way to decide two snapshots may be ranked together.
- Tests use fixture `MethodStatusSnapshot`/`VetoAssessmentResult` values
  loaded against the real `configs/formulas/v1.yaml`, never live evidence,
  model, or database calls.
