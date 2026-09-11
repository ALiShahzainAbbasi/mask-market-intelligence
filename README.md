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
22. [`docs/WORKFLOW_INTELLIGENCE.md`](docs/WORKFLOW_INTELLIGENCE.md) — accepted workflow-step ingestion, exact step-name grouping, formula-v1 M3 bottleneck calculation, and report lineage.
23. [`docs/CONFIDENCE_AND_VETOES.md`](docs/CONFIDENCE_AND_VETOES.md) — formula-v1 confidence aggregation, sample adequacy, completeness classification, and automatic detection of the three purely-numeric vetoes.
24. [`docs/REPORTING.md`](docs/REPORTING.md) — the JSON/HTML/CSV market research report: outputs, next-action priority order, and what is deferred (PDF) or pending real data (A17.5).
25. [`docs/YOUTUBE_DATA.md`](docs/YOUTUBE_DATA.md) — the A17.5 YouTube Data API adapter: search/commentThreads scope, quota accounting, and the held live-smoke gate.
26. [`docs/ONET_DATA.md`](docs/ONET_DATA.md) — the A17.5 O*NET database bootstrap/cache/import pipeline for M3 occupation/task mapping.
27. [`docs/COMMON_CRAWL.md`](docs/COMMON_CRAWL.md) — the A17.5 targeted Common Crawl retriever: CDX lookup, ranged WARC fetch, and reuse of the existing static-HTML parse/normalize pipeline.

## Precedence

The research methodology and approved overall weights are business policy. Engineering proposals such as internal subweights and evaluation thresholds are versioned configuration. If a proposed detail conflicts with an approved methodology rule, the methodology rule wins.

## Current status

- Phase 0: baseline accepted; the autonomous specification now supplies the approved v1 numerical formulas.
- Phase 1: 6/10 checkpoints complete. The native Windows setup, PostgreSQL queue/worker, and Supabase-backed database migration path are implemented; remaining hosted/operational acceptance stays tracked separately.
- Phase 2: 1/7 checkpoints complete. Supabase PostgreSQL 17/pgvector is at Alembic 0006 with private `mask` tables and a least-privilege runtime role. Local auth code exists but its HTTP boundary remains disabled and is not a functional-track blocker.
- Phase 3: in progress; immutable source-policy/document contracts, policy and URL gates, bounded public-HTTP fetching, RSS/Atom and static-HTML parsers, versioned normalization, exact duplicate lineage, finite retry/circuit/cancellation behavior, and a typed persistence boundary are offline-tested. No real source or database adapter is wired, so no Phase 3 checkpoint is complete.
- Autonomous functional track: A01-A05, A10-A17 are complete. The fixed-scope Census CBP, keyless BLS, BEA Regional, SEC EDGAR, and SAM.gov adapters passed one deliberately small live check each; A17.5 adds a sixth, keyless official_data source (USAspending award search for M4/M5). Gemini and YouTube Data API credentials are now configured locally (owner-supplied); live wiring for both is in progress under the free-source real-data expansion (A17.5). A06/A07 remain partial while other providers stay on hold; A09's offline structured-analysis boundary is implemented, and A17.5 has now added a Gemini `generateContent` provider mirroring it exactly, plus a separate `youtube_data` module for `search.list`/`commentThreads.list` with its own quota-unit accounting (both offline-tested against fake transports only; no live call made for either yet, and both stay disabled until explicit policy approval), an `onet_data` module that bootstraps/caches/imports the official O*NET downloadable database for M3, and a `common_crawl_data` module for targeted CDX-lookup-plus-ranged-WARC-fetch historical retrieval that reuses the existing static-HTML parse/normalize pipeline (live-verified end to end).
- Modularity: thin composition roots, injectable ports, pure scoring/query/taxonomy/grounding/M2/M3/method-metric/confidence/market-scoring/reporting rules, provider transports separated from planning/persistence, explicit CLI adapter boundaries, module-scoped instructions, and executable architecture checks. Overall roadmap is 31/172 complete after A17; partial work is not counted as complete.
- Current local checks: all 5 original official-data live smokes pass, plus a new live Common Crawl smoke (real CDX lookup + ranged WARC fetch against `example.com`) and O*NET's live smoke (real ~16MB download + import, passed on a third attempt after two earlier attempts found and fixed a real silent-truncation bug -- see `docs/ONET_DATA.md`). USAspending's own gated live smoke test has not been run as a test, though its live data path was proven separately by direct ingestion. The complete offline suite passes with 701 Python and 11 web tests, including A09-A17 extraction, grounding, M2 pain intelligence, M3 workflow-bottleneck calculation, the M1/M4/M5/M6/M7/M9 formula calculators, the confidence/completeness/automatic-veto engine, the automated-research-score/gate/snapshot engine, the JSON/HTML/CSV report generator, the A17.5 Gemini/YouTube/USAspending/O*NET/Common-Crawl source suites, and the first real `MethodExecutor` (`CensusM1Executor`). The static gates are recorded in `progress.txt`. Supabase acceptance remains recorded there; no paid research ran.
- First real scored result: run live against the `us_hvac_10_99` sample market, `CensusM1Executor` (`mask_api.research_runner.executors`) produced the system's first genuine, source-grounded M1 score -- **6.34/10, status `complete`** -- entirely from real 2017/2022 Census CBP data (23,617 real establishments in the target employee band, a real 2.25% five-year CAGR, a real 71.2% under-100-employee employment share, real average payroll per establishment), every component traceable to an exact Census query. It owns no source or scoring logic itself, only wiring the existing `official_data` Census adapter into the existing `method_metrics.calculate_m1` calculator. Not yet registered with the `ResearchRunner` CLI's `executors=` list.
- Native service preflight reports missing/unready services and exits nonzero. It does not require a container runtime or silently substitute mocks. This is a local scaffold, not a deployed or production-ready application.
- Next code: continuing the free-source real-data expansion (A17.5) -- the provider-independent source/evidence fallback registry with Tier A-E quality classes, then more `MethodExecutor` implementations beyond the first (`CensusM1Executor`), and registering executors with the `ResearchRunner` CLI -- aimed at one real, source-backed market report at $0 paid-data cost. Google Ads, Reddit, Google Places, Meta, Brave, and firmographic providers remain held/optional. No paid provider, outreach, campaign, or deployment was activated.
- Running-app authentication, market CRUD/UI, live scrapers, integrations, AI analysis, and scoring are not enabled. Collector code exists as an offline-tested shared service, but a real approved source policy and persistence adapter are mandatory before worker or API composition.
- Live checkpoint status: [`progress.txt`](progress.txt). The existing Phase 0 ZIP is a historical snapshot, not the live tracker.
