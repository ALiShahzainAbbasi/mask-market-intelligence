# Workflow intelligence module rules

Read the root `AGENTS.md`, `progress.txt`, `docs/RESEARCH_METHODOLOGY.md`,
`docs/SCORING.md`, `docs/AI_PIPELINE.md`, `docs/EVALUATION.md`,
`docs/COST_CONTROL.md`, and `docs/MODULARITY.md` before changing this module.

- Accept only A10 reports with `eligible_for_scoring_input=true`; preserve their
  analysis/document/source lineage and never accept raw model output directly.
- Keep ingestion, bottleneck calculation, and orchestration in separate modules
  behind typed contracts, matching `pain_intelligence`'s boundary.
- Workflow steps are grouped by an exact normalized-step-name hash, not semantic
  clustering: a step has a natural identity (what an operator/analyst named it),
  unlike free-text pain mentions. Never merge steps by embedding similarity.
- Duplicate evidence never increases a step's volume/labor/etc. component
  values: they are averaged across the step's evidence, not summed, and
  `evidence_count` (used as the sqrt-weight in market aggregation) is the
  number of *distinct* evidence records, never inflated by re-ingesting the
  same document/record twice (rejected by a unique `evidence_id` check).
- Formula execution consumes the validated v1 `MethodFormula`; do not copy
  weights into prompts/UI. If any non-empty step is missing a required
  component, the whole M3 result stays UNKNOWN — never silently drop that step
  from ranking or renormalize around it. There is no v1 M3 sample/partial-
  completeness rule, so a known M3 result is always `complete`, never
  `provisional`.
- "No unvalidated AI-generated workflow supports a high-confidence score" is a
  confidence-engine (P13) responsibility, not this module's: v1's M3
  completeness rule is purely about component availability. Do not invent an
  extra blocking gate here that v1 does not define.
- Tests use labelled evidence records only. Fixtures are not market evidence
  or production AI evaluation.
