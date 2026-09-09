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

The lean default source profile also carries an executable operational status.
Paid, credential-pending, and approval-pending sources stop before network access
and do not block later deterministic pipeline work. See
`docs/SOURCE_AVAILABILITY.md` for the current owner-approved holds and fallback
rules.
