# Pain intelligence module rules

Read the root `AGENTS.md`, `progress.txt`, `docs/RESEARCH_METHODOLOGY.md`,
`docs/SCORING.md`, `docs/AI_PIPELINE.md`, `docs/EVALUATION.md`,
`docs/COST_CONTROL.md`, and `docs/MODULARITY.md` before changing this module.

- Accept only A10 reports with `eligible_for_scoring_input=true`; preserve their
  analysis/document/source lineage and never accept raw model output directly.
- Keep ingestion, embedding, exact/near dedupe, clustering, M2 calculation, and
  orchestration in separate modules behind typed contracts.
- Deduplicate before clustering. Duplicate mentions never increase frequency,
  component means, source diversity, sample adequacy, or cluster weight.
- Never cluster across personas. Unknown is a persona, not permission to merge it
  with owner, employee, customer, vendor, manager, or executive evidence.
- Embedding model/version/dimensions/input hash and clustering algorithm/version/
  thresholds/input hash are immutable lineage. No provider fallback or silent
  model/version upgrade is permitted.
- Local lexical hashing is a zero-cost deterministic MVP adapter, not a claim of
  semantic-model quality. A later provider remains injected and budgeted.
- Formula execution consumes the validated v1 `MethodFormula`; do not copy
  weights into prompts/UI. Missing required values or inadequate samples remain
  UNKNOWN, never zero. Sentiment remains separate from severity.
- Cluster names are deterministic category labels unless an A09/A10-grounded,
  human-approved naming result is supplied later. Models never choose membership
  or calculate metrics/scores.
- Tests use labelled records and deterministic vectors only. Fixtures and local
  hashing output are not market evidence or production AI evaluation.
