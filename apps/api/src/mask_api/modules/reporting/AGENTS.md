# Reporting module rules

Read the root `AGENTS.md`, `progress.txt`, `docs/SCORING.md`, and
`docs/MODULARITY.md` before changing this module.

- This is a pure presentation layer over `market_scoring`'s
  `MarketScoreSnapshot`. It performs **no calculation**: it never derives a
  score, confidence value, gate result, or veto finding -- it only reads,
  summarizes deterministically, and renders what those modules already
  computed.
- `executive_summary` and `next_recommended_action` are template-generated
  from already-computed numbers, not free-form prose. If a future Gemini
  narrative-summarization layer is added (A17.5), it must consume this
  report's already-validated fields as its only input and must never be
  allowed to alter a score, confidence, gate result, or veto -- see
  `docs/AI_PIPELINE.md`'s LLM boundary rules.
- `MethodReportEntry.detail` is the method's own already-validated result
  (`M2Result`/`M3Result`/`MethodMetricResult`, dumped to JSON by the
  caller). This module does not import those calculators or reshape their
  internals; it only carries the blob through.
- HTML rendering escapes every interpolated value via `html.escape`, with
  no exceptions. Once A17.5 wires in real web-derived evidence text, report
  content will include untrusted strings; nothing here may assume evidence
  text is safe markup.
- `SourceAttemptOutcome` records what a specific run actually did with a
  source (`successful`/`unavailable`/`source_unavailable_quota`/
  `not_relevant`). A source the run never tried stays entirely absent from
  `source_attempts` -- never backfill it with an invented "not attempted"
  row.
- PDF rendering is intentionally not implemented here: it would require a
  new rendering dependency (weasyprint/reportlab-class library) this
  project has not evaluated or approved. HTML output is print-to-PDF-ready
  in any browser; add a PDF renderer only after an explicit approval, not
  silently.
- Tests use fixture `MarketScoreSnapshot`/`SourceProfile` values loaded
  against the real `configs/formulas/v1.yaml`/`configs/sources/
  default_us_public.yaml`, never live evidence, model, or database calls.
