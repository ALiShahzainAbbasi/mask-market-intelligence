# MASK AI Market Intelligence & Selection System

Private GitHub repository: <https://github.com/ALiShahzainAbbasi/mask-market-intelligence>

Phase 0 is the accepted baseline. Supabase PostgreSQL/pgvector and the private
application role are live, while the CLI-first A01-A20 functional build proceeds
independently of optional authentication/UI work. A01 establishes the exact
versioned M1-M10 formulas, strict market/source configuration, reproducible
hashing, and deterministic shared math. Auth and collection routes remain
unregistered until their tenant and live acceptance requirements pass.

The system is designed to answer: which market should MASK AI target, why, how confident are we, what supports and contradicts the conclusion, and what remains to be proven?

## Canonical documents

Local setup, commands, migrations, environment variables, and troubleshooting: [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md). Runtime/tool decisions: [`ADR 0001`](docs/decisions/0001-phase-1-baseline.md).

Development is container-free under [ADR 0002](docs/decisions/0002-container-free-development.md), and [ADR 0003](docs/decisions/0003-windows-first-lean-runtime.md) makes the private MVP Windows-native and lean. After configuring the pinned Node/pnpm/Python/uv tools and running `pnpm run setup`, use separate terminals for `pnpm dev:api`, `pnpm dev:worker`, and `pnpm dev` (web). The worker uses the durable PostgreSQL queue directly and defaults to one job at a time.

Modularity is mandatory in [AGENTS.md](AGENTS.md), scoped app/worker instructions, and [docs/MODULARITY.md](docs/MODULARITY.md). Static boundary/cycle tests run in the regular quality suite.

The implemented identity interfaces, preliminary role matrix, trust boundaries, and remaining sign-in requirements are in [docs/AUTHORIZATION.md](docs/AUTHORIZATION.md).

Start with [`progress.txt`](progress.txt) for the full Phase 0–24 roadmap, checkpoint status, completed/remaining counts, pending decisions, and work history. Update it after every checkpoint; `AGENTS.md` makes this part of the project workflow.

1. [`docs/PRODUCT.md`](docs/PRODUCT.md) — product purpose, users, workflow, stages, and success criteria.
2. [`docs/RESEARCH_METHODOLOGY.md`](docs/RESEARCH_METHODOLOGY.md) — the ten-method research system and human/automation boundaries.
3. [`docs/SCORING.md`](docs/SCORING.md) — approved weights, deterministic scoring, confidence, gates, vetoes, and overrides.
4. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — system boundaries, runtime topology, modules, and evidence lineage.
5. [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) — canonical entities, relationships, immutability, and audit rules.
6. [`docs/SCRAPING_POLICY.md`](docs/SCRAPING_POLICY.md) — permitted collection, source registration, rate limits, and retention.
7. [`docs/AI_PIPELINE.md`](docs/AI_PIPELINE.md) — AI responsibilities, structured extraction contracts, versioning, and validation.
8. [`docs/EVALUATION.md`](docs/EVALUATION.md) — labelled datasets, metrics, release gates, and regression testing.
9. [`docs/SECURITY.md`](docs/SECURITY.md) — access, secrets, sensitive research data, and operational controls.
10. [`docs/phases/PHASE_1_CHECKLIST.md`](docs/phases/PHASE_1_CHECKLIST.md) — the implementation checklist for repository and infrastructure setup.
11. [`docs/phases/PHASE_2_CHECKLIST.md`](docs/phases/PHASE_2_CHECKLIST.md) — identity, tenant-scoped market schema, authentication, registry UI, and end-to-end acceptance.
12. [`docs/COST_CONTROL.md`](docs/COST_CONTROL.md) — mandatory lean research limits, paid-model hard stops, and deferred scope.
13. [`docs/COLLECTORS.md`](docs/COLLECTORS.md) — implemented collector boundaries, pipeline, safety limits, fixtures, and remaining live-integration work.
14. [`docs/AUTONOMOUS_RESEARCH_MODE.md`](docs/AUTONOMOUS_RESEARCH_MODE.md) — CLI-first functional track, versioned configuration, module boundaries, outputs, and hard safety/cost rules.
15. [`docs/DISCOVERY.md`](docs/DISCOVERY.md) — deterministic method-aware query plans and the disabled-by-default Brave Search discovery boundary.
16. [`docs/OFFICIAL_DATA.md`](docs/OFFICIAL_DATA.md) — fixed-scope official US API adapters, credentials, hard limits, provenance, and live-smoke gates.
17. [`docs/SOURCE_AVAILABILITY.md`](docs/SOURCE_AVAILABILITY.md) — explicit available, credential/approval-pending, and paid-hold source behavior.
18. [`docs/SEARCH_INTENT.md`](docs/SEARCH_INTENT.md) — versioned keyword-intent taxonomy, historical-metrics contracts/cache, and the held Google Ads boundary.
19. [`docs/ANALYSIS_PROVIDER.md`](docs/ANALYSIS_PROVIDER.md) — strict structured-extraction contracts, cache, and the held OpenAI Responses boundary.
20. [`docs/GROUNDING_VALIDATION.md`](docs/GROUNDING_VALIDATION.md) — exact-span/numeric validation, contradiction preservation, injection review, and independent high-impact verification.
21. [`docs/PAIN_INTELLIGENCE.md`](docs/PAIN_INTELLIGENCE.md) — accepted pain ingestion, duplicate-safe embeddings/clustering, formula-v1 M2 calculation, and report lineage.

## Precedence

The research methodology and approved overall weights are business policy. Engineering proposals such as internal subweights and evaluation thresholds are versioned configuration. If a proposed detail conflicts with an approved methodology rule, the methodology rule wins.

## Current status

- Phase 0: baseline accepted; the autonomous specification now supplies the approved v1 numerical formulas.
- Phase 1: 6/10 checkpoints complete. The native Windows setup, PostgreSQL queue/worker, and Supabase-backed database migration path are implemented; remaining hosted/operational acceptance stays tracked separately.
- Phase 2: 1/7 checkpoints complete. Supabase PostgreSQL 17/pgvector is at Alembic 0006 with private `mask` tables and a least-privilege runtime role. Local auth code exists but its HTTP boundary remains disabled and is not a functional-track blocker.
- Phase 3: in progress; immutable source-policy/document contracts, policy and URL gates, bounded public-HTTP fetching, RSS/Atom and static-HTML parsers, versioned normalization, exact duplicate lineage, finite retry/circuit/cancellation behavior, and a typed persistence boundary are offline-tested. No real source or database adapter is wired, so no Phase 3 checkpoint is complete.
- Autonomous functional track: A01-A05 and A10-A11 are complete. The fixed-scope Census CBP, keyless BLS, BEA Regional, SEC EDGAR, and SAM.gov adapters passed one deliberately small live check each. A06/A07 remain partial while skipped providers stay on hold; A09's offline structured-analysis boundary is implemented and remains partial because live model use is held.
- Modularity: thin composition roots, injectable ports, pure scoring/query/taxonomy/grounding/M2 rules, provider transports separated from planning/persistence, explicit CLI adapter boundaries, module-scoped instructions, and executable architecture checks. Overall roadmap is 25/171 complete after A11; partial work is not counted as complete.
- Current local checks: all 5 official-data live smokes pass; the complete offline suite passes with 440 Python and 11 web tests, including A09-A11 extraction, grounding, and M2 pain intelligence. The static gates are recorded in `progress.txt`. Supabase acceptance remains recorded there; no paid research ran.
- Native service preflight reports missing/unready services and exits nonzero. It does not require a container runtime or silently substitute mocks. This is a local scaffold, not a deployed or production-ready application.
- Next code: build A12's exact M1/M4/M5/M6/M7 source-to-metric transforms and deterministic formula-v1 calculators while Google Ads, YouTube, Reddit, Meta, Google Places, Brave, firmographics, and live model use remain held. Census, BEA, SAM.gov, keyless BLS, SEC EDGAR, approved feeds/pages, and later validated analyst inputs are the lean source set. No paid provider, outreach, campaign, or deployment was activated.
- Running-app authentication, market CRUD/UI, live scrapers, integrations, AI analysis, and scoring are not enabled. Collector code exists as an offline-tested shared service, but a real approved source policy and persistence adapter are mandatory before worker or API composition.
- Live checkpoint status: [`progress.txt`](progress.txt). The existing Phase 0 ZIP is a historical snapshot, not the live tracker.
