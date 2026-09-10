# Autonomous Research Mode

Status: A01 implementation contract, approved from the owner-supplied Autonomous
Market Intelligence Engine Build Specification v1.

## Goal and command contract

The functional track is a Windows-native, CLI-first research pipeline. Its target
interface is:

```powershell
uv run python -m mask_api.research_runner run configs/markets/<market>.yaml --methods all --output outputs/runs/<run_id>
```

The A03 command is implemented. It loads and hashes all three configuration
contracts, explicitly selects local artifact persistence, writes append-only
method/run checkpoints, and safely resumes a compatible interrupted or terminal
run. Exit code `0` means every selected installed method succeeded, `2` means an
honest partial result, and `1` means the run could not safely proceed.

A completed A17 run will additionally produce raw and normalized evidence,
extracted evidence, metrics, logs, score and confidence breakdowns, unknowns, a
source manifest CSV, `report.json`, HTML, and PDF. Partial results are retained
when a bounded source fails or a hard limit is reached.

## Versioned inputs

- `configs/markets/*.yaml` defines the market, geography, NAICS codes, company
  band, buyers, seed terms/problems, research window, validation budget, source
  profile, and formula version. Unknown fields and invalid ranges fail before any
  work starts. `configs/schemas/market.schema.json` is generated from the runtime
  contract and checked for drift.
- `configs/formulas/v1.yaml` is the executable source for the exact M1-M10
  weights, transforms, aggregation rules, completeness/sample thresholds,
  confidence formula, gates, and veto triggers. A change requires a new version;
  historical runs retain their version and canonical SHA-256.
- `configs/sources/*.yaml` declares allowed access modes, evidence use, method
  coverage, policy state, credentials, cost class, and signal fallbacks. Every
  network source is disabled by default.

YAML is loaded through strict frozen Pydantic contracts in
`mask_api.research_runner`. The validated value—not whitespace or key order—is
canonically hashed for reproducibility.

## Modular execution boundary

```text
CLI adapter -> ResearchRunner use case -> discovery/collection/extraction ports
                                |       -> method calculators and gate rules
                                +------> artifact persistence port
```

The runner coordinates work but owns no HTTP, SQL, prompt, scoring, or rendering
implementation. Collectors return source-grounded data through narrow ports.
Deterministic scoring lives in `mask_api.modules.scoring`. A02 provides an
explicit `LocalArtifactStore` adapter for CLI runs through a narrow artifact
persistence port; it never silently replaces PostgreSQL in API/worker wiring.

The local adapter writes immutable artifacts atomically beneath fixed `raw`,
`normalized`, `evidence`, `metrics`, `reports`, `manifests`, `lineage`, and `logs`
directories. It preserves exact bytes, returns SHA-256 receipts, treats an
identical repeat as an idempotent success, rejects a conflicting rewrite, blocks
unsafe Windows/POSIX paths, and enforces file/count/run byte limits. Generated
run directories under `outputs/runs/` are intentionally ignored by Git.

## Non-negotiable behavior

- Missing, blocked, invalid, or insufficient evidence is `UNKNOWN`, never zero or
  an invented estimate. Required UNKNOWN values make the method incomplete.
- LLMs may extract/classify/verify evidence but never calculate scores,
  confidence, rankings, vetoes, gates, or recommendations.
- Raw evidence, normalized evidence, exact spans, numeric provenance,
  contradictions, source attempts, and configuration hashes remain auditable.
- M8 and M10 remain UNKNOWN until real, qualified evidence exists. Fixtures,
  simulations, and inferred funnel values cannot satisfy them.
- Paid collection, models, outreach, and campaigns are off by default. Each needs
  explicit enablement, credentials, policy approval, and a positive owner-approved
  budget. The runner stops before a limit would be exceeded.
- Collection never bypasses authentication, CAPTCHAs, paywalls, robots controls,
  rate limits, or other access restrictions.

The initial sample market is `configs/markets/us_hvac_10_99.yaml`. It is a
configuration fixture, not completed market research and not evidence of a score.

Its `run_budget` explicitly caps requests, documents, fetched bytes, duration,
and paid cost. Adapters reserve measured work through the shared `BudgetLedger`
before performing it. A reached limit stops subsequent method dispatch, preserves
completed checkpoints, and marks unexecuted methods UNKNOWN. M8/M10 remain UNKNOWN
when validation is disabled even if an executor is installed.

## Implemented source edges

A04 provides pure method-aware discovery queries and an optional, paid-budget
gated Brave Search edge. A05 adds fixed-scope official API edges for Census CBP,
BLS, BEA Regional, SEC EDGAR submissions, and SAM.gov opportunities. Each official
edge separates request validation, secrets, transport, parsing, and provenance;
all remain disabled without explicit policy approval. See
`docs/OFFICIAL_DATA.md` for endpoint, credential, limit, and live-smoke details.

These edges are source capabilities, not method results. They are intentionally
not wired into the CLI until the method transformations/executors can turn their
records into the exact versioned metrics without inventing missing values.

A09 provides eight versioned structured-extraction schemas and a disabled,
injected OpenAI Responses boundary. A10 adds the mandatory offline grounding gate:
exact spans, numeric support, contradiction preservation, prompt-injection review,
and independent verification of high-impact claims. Only an accepted grounding
report exposes future scoring input; model use remains held and disabled.

A11 consumes that accepted boundary through a separate M2 pain module. It applies
duplicate-safe persona-separated processing, a cached zero-cost local lexical
embedding adapter, deterministic clustering/outliers, the exact formula-v1 M2
cluster and top-five aggregation, UNKNOWN/provisional sample rules, contradiction
lineage, and a generated report schema. A later semantic provider remains an
injected option and is not enabled by default.

A12 adds `mask_api.modules.method_metrics`: typed, source-grounded metric and
provenance contracts plus the exact formula-v1 M1/M4/M5/M6/M7 source-to-metric
transforms and calculators. Every component transform (`linear`, `reverse_linear`,
`log_scale`, `multiply`, `complement`, and the M5/M7 weighted/composite
calculations) consumes only explicitly available normalized values; a missing
required component keeps the whole method UNKNOWN and the weighted sum is never
renormalized around it. M1/M5/M6 retain the v1 partial-completeness/sample rules
and can be PROVISIONAL; M4/M7 have no such rule and are strictly UNKNOWN/COMPLETE.
These calculators are not yet wired into the CLI's `MethodExecutor` protocol or
into `official_data`/`search_intent` adapters; like A11's `PainIntelligenceService`,
that composition is later work once source-to-metric mapping for each provider is
approved.

A13 adds `mask_api.modules.workflow_intelligence` and a ninth analysis schema,
`workflow-step-v1`. It consumes A10-accepted workflow-step extraction the same
way A11 consumes A10-accepted pain extraction, but groups evidence by an exact
normalized step-name hash instead of embeddings/clustering, since a
reconstructed workflow step has a natural identity. Per-step component means
feed the exact v1 M3 transforms (log_scale for volume/labor burden, linear for
failure rate/manuality, identity for consequence/automation potential); any
missing component on any step keeps the whole result UNKNOWN. The market score
is the same max-plus-sqrt(evidence-count)-weighted-top-five aggregation A11
uses for M2. `WorkflowIntelligenceService` is not yet wired into the CLI's
`MethodExecutor` protocol, matching A11/A12's precedent.

A14 extends `mask_api.modules.method_metrics` with `m9.py`, the exact v1 M9
MASK AI/productization-fit calculator, since M9 uses the same `weighted_sum`
aggregation as M1/M4/M6/M7 rather than M2/M3's clustering-style pattern.
Two components have their own typed composite inputs rather than a single
`SourcedMetric`: `technical_fit` needs a capability registry
(`CapabilityRequirement`, weighted by importance) crossed against a
technical/business reviewer's coverage assessment (`CapabilityCoverage`) via
the new `weighted_coverage` transform, and `integration_fit` needs integration
discovery (`IntegrationRecord`: a target-market platform's prevalence and
whether MASK AI supports it) summed to a supported-platform-prevalence ratio.
Per `RESEARCH_METHODOLOGY.md`, M9 assessment is leadership/technical-reviewer
owned and AI may only organize evidence; this module accepts already-decided
`covered`/`supported` judgments and never infers them. A capability with no
matching coverage record keeps the whole M9 result UNKNOWN rather than being
dropped from the weighted-coverage sum.

A15 adds `mask_api.modules.confidence`, sitting above the method calculators
and consuming their public result contracts. It implements the exact v1
confidence-aggregation formula (given the five dimensions as already-
normalized 0-10 inputs), `sample_adequacy` scoring against v1's approved
per-method targets, Proven/Weak/Missing/Not-applicable completeness
classification, and automatic detection of the three v1 vetoes with a purely
numeric trigger (`no_meaningful_budget`, `no_reachable_economic_buyer`,
`highly_bespoke_delivery`). It deliberately does not derive
`source_diversity`/`evidence_quality`/`recency`/`cross_source_agreement`
from raw evidence (per-method normalizers for those remain open decision D04)
and honestly reports the other three vetoes as not-evaluated rather than
inventing the evidence contracts or M8/M10 data they need. See
`docs/CONFIDENCE_AND_VETOES.md`.

A16 adds `mask_api.modules.market_scoring`, the top of the calculation
stack. `AutomatedResearchScore` is the raw (never renormalized) sum of
available weighted method contributions -- explicitly not the market's
approved score, matching SCORING.md's "provisional contribution" language.
`FinalValidatedScore` stays `not_ready` in every run today, honestly,
because no reviewed-score human-approval workflow exists yet (P12).
`aggregate_confidence` computes gate and overall confidence via the one
renormalization SCORING.md approves (across a required-method subset, never
to conceal a missing score). `evaluate_gate` implements the exact five-state
gate result taxonomy (`not_ready`/`blocked`/`eligible_to_advance`/
`does_not_meet_gate`/`founder_review_required`) with a confirmed critical
veto always taking priority. `build_market_score_snapshot` composes all of
this into one immutable, reproducible snapshot; `snapshots_are_comparable`
is the only approved way to decide two snapshots may be ranked together.
Snapshots are persisted through the CLI's `LocalArtifactStore`, the same
file-based pattern every research run already uses -- the DATA_MODEL.md
`market_score_snapshots` table remains unimplemented (P02/P03/P13 work),
which this checkpoint does not build ahead of schedule.

A17 adds `mask_api.modules.reporting`, a pure presentation layer over one
`MarketScoreSnapshot`: `report.json` (machine-readable), a self-contained
static HTML report (every value `html.escape`d, since A17.5 will feed it
real web-derived evidence text that must never be trusted as safe markup),
and a CSV source manifest joining the registered source inventory against
what a specific run actually attempted. `executive_summary` and
`next_recommended_action` are template-generated from already-computed
numbers, following SCORING.md section 7's priority order (confirmed veto,
then suspected veto, then the nearest gate-blocking missing method, then
lower-priority completeness) -- no free-form or model-generated prose. PDF
rendering is intentionally deferred: it would need a new rendering
dependency this project has not evaluated; HTML output is print-to-PDF
ready in any browser today.

The lean default source profile also carries an executable operational status.
Paid, credential-pending, and approval-pending sources stop before network access
and do not block later deterministic pipeline work. See
`docs/SOURCE_AVAILABILITY.md` for the current owner-approved holds and fallback
rules.
