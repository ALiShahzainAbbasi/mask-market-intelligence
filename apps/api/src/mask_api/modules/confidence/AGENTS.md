# Confidence module rules

Read the root `AGENTS.md`, `progress.txt`, `docs/SCORING.md` sections 6-9,
`docs/AUTONOMOUS_RESEARCH_MODE.md`, and `docs/MODULARITY.md` before changing
this module.

- This module sits above the method calculators: it consumes their public
  result contracts (`method_metrics.MethodMetricResult`, and later
  `pain_intelligence.M2Result`/`workflow_intelligence.M3Result`), never their
  internal calculation helpers. It never computes a method score itself.
- `calculate_confidence` requires all five v1 dimensions as **explicit,
  already-normalized 0-10 inputs**. It does not derive `source_diversity`,
  `evidence_quality`, `recency`, or `cross_source_agreement` from raw
  evidence: SCORING.md section 6 says those normalizers are "versioned
  alongside each method rubric," and none exist in `configs/formulas/v1.yaml`
  yet (open decision D04 in `progress.txt`). Do not invent one here, even as
  a "reasonable default" — that is exactly the kind of unapproved
  methodology change `docs/SCORING.md` forbids. A missing dimension keeps
  confidence UNKNOWN, never a partial/renormalized weighting.
- `sample_adequacy_score` is the one dimension with an approved, generic
  derivation, because v1.yaml's `confidence.sample_targets` gives an exact
  target per method (matching that method's own `sample.full_target`). Only
  M2/M5/M6/M8/M10 have a target; every other method's sample adequacy stays
  UNKNOWN through this function, honestly, until D04 approves more.
- `classify_completeness` is a pure status → Proven/Weak/Missing mapping. Do
  not add quality/recency/diversity thresholds here — that is confidence's
  job, not completeness's, per SCORING.md's "Completeness is not confidence
  and not score."
- `evaluate_automatic_vetoes` implements only the three v1 vetoes with a
  pure numeric trigger (`no_meaningful_budget`, `no_reachable_economic_buyer`,
  `highly_bespoke_delivery`). The other three always come back in
  `not_evaluated`: two need an explicit human-verified evidence contract
  (`major_access_or_regulatory_barrier`, `dominant_platform_solves_problem`)
  that does not exist yet, and one needs M8/M10 data (A18/A19). Do not wire
  a placeholder/default evidence flag to "complete" these three — leave them
  honestly unevaluated until their real inputs exist.
- A veto's trigger condition being met makes it `suspected`; `confirmed`
  additionally requires the exact confidence label v1.yaml's trigger text
  names (HIGH, or MEDIUM-or-HIGH for `highly_bespoke_delivery`). `resolved`
  and `accepted_exception` are human review-workflow states (P18), out of
  this module's automatic-detection scope — never assign them here.
- Every v1 veto is `critical` severity (v1.yaml's `vetoes` block defines only
  vetoes, not a broader warning taxonomy); do not invent a `warning` tier.
- Tests use fixture `MethodMetricResult`/`ConfidenceResult` values, never
  live evidence, model, or database calls.
