# Market Research Report

Status: A17 offline implementation.

`mask_api.modules.reporting` renders one `MarketScoreSnapshot`
(`market_scoring`, A16) into three output formats. It performs no
calculation of its own -- every number, label, and status it presents was
already computed by `confidence`, the method calculators, or
`market_scoring`.

## Outputs

- **`report.json`** (`render_json_report`) -- the full `ReportPackage`
  contract, machine-readable, deterministic for identical input.
- **`report.html`** (`render_html_report`) -- a self-contained static page
  (no external assets, no template engine). Every interpolated value passes
  through `html.escape`, without exception: once A17.5 wires in real
  web-derived evidence text, report content will include untrusted strings.
- **CSV source manifest** (`render_source_manifest_csv`) -- the registered
  source inventory joined against what a specific run actually attempted
  (`SourceAttemptOutcome`). A source the run never tried stays entirely
  absent from the attempt columns rather than being backfilled with an
  invented "not attempted" row.

PDF rendering is intentionally deferred: it would require a new rendering
dependency (a weasyprint/reportlab-class library) this project has not
evaluated or approved. HTML output is print-to-PDF ready in any browser
today; add a PDF renderer only after an explicit approval.

## Executive summary and next action

`executive_summary` and `next_recommended_action` are template-generated
from already-computed fields, not free-form or model-generated prose.
`recommend_next_action` follows SCORING.md section 7's priority order:

1. a confirmed critical veto (investigate it);
2. a suspected veto (investigate it);
3. the nearest not-ready gate's first missing required method;
4. any method still missing from the automated research score;
5. otherwise, "awaiting reviewed-score approval and further gate
   progression."

If a future Gemini narrative-summarization layer is added (A17.5), it may
only consume this report's already-validated fields as its input -- it must
never be allowed to alter a score, confidence, gate result, or veto. See
`docs/AI_PIPELINE.md`'s LLM boundary rules.

## Report contents today vs. after A17.5

Every field the report package defines is populated deterministically from
whatever `MarketScoreSnapshot`/method detail it is given. Before A17.5 wires
real collectors, that input is necessarily test/fixture data -- a report
built today is a template proof, not market evidence. `source_attempts`
(sources actually tried this run) and rich per-method `detail` blobs are
designed to be populated once A17.5's `MethodExecutor` wiring exists; until
then, callers may omit them and the report renders honestly with what it
has (an empty attempts table, `detail: null` per method).
