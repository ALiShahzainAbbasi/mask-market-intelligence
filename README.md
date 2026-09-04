# MASK AI Market Intelligence & Selection System

Private GitHub repository: <https://github.com/ALiShahzainAbbasi/mask-market-intelligence>

Phase 0 is the accepted baseline. Phase 1/2 live database acceptance is deferred, while the user has authorized Phase 3 collector code. The modular monolith now includes the earlier identity/market/authentication core plus a policy-gated evidence pipeline and two offline-tested collectors for RSS/Atom and permitted static HTML. Auth and collection routes remain unregistered until their database, tenant, and live acceptance requirements pass, so the running app does not yet expose sign-in, market, or collection workflows.

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

## Precedence

The research methodology and approved overall weights are business policy. Engineering proposals such as internal subweights and evaluation thresholds are versioned configuration. If a proposed detail conflicts with an approved methodology rule, the methodology rule wins.

## Current status

- Phase 0: baseline accepted for infrastructure work; numerical proposals remain pending.
- Phase 1: 5/10 checkpoints complete. The PostgreSQL-backed Windows queue/worker implementation is written and offline-tested; real PostgreSQL lease/recovery and operator acceptance remain open before its checkpoints can close.
- Phase 2: in progress; identity/market schema, authorization, local credential/session services, transactional repositories, Alembic 0004, bootstrap CLI, and inactive auth HTTP adapter are written. Live migration, bootstrap, browser registration, and market authorization remain; no Phase 2 checkpoint is complete.
- Phase 3: in progress; immutable source-policy/document contracts, policy and URL gates, bounded public-HTTP fetching, RSS/Atom and static-HTML parsers, versioned normalization, exact duplicate lineage, finite retry/circuit/cancellation behavior, and a typed persistence boundary are offline-tested. No real source or database adapter is wired, so no Phase 3 checkpoint is complete.
- Modularity: thin API composition, feature routers, injectable services/ports, pure policies, source parsers separated from network/persistence, shared worker use cases, module-scoped instructions, and executable architecture checks. Overall roadmap remains 16/151 complete; partial schema/identity/collector work is not counted as a finished checkpoint.
- Current local checks: 229 tests pass (218 Python + 11 web), including 36 collector-focused cases, with Python/web lint/format, strict types across 83 Python source files, architecture, generated API/TS contracts, offline migrations, setup-preservation, queue/worker behavior, and local-auth contracts passing. Twenty-four real PostgreSQL/service cases remain unrun. The 48-package lock remains unchanged and verified from the prior auth slice.
- Native service preflight reports missing/unready services and exits nonzero. It does not require a container runtime or silently substitute mocks. This is a local scaffold, not a deployed or production-ready application.
- Next code while database work is deferred: P03-04 safe upload/manual-capture validation. Later P03 work must add the evidence migrations, transactional PostgreSQL policy/evidence adapters, tenant-authorized job wiring, and small approved live-source smoke tests. No remote, paid provider, account, live collection, or deployment was created.
- Running-app authentication, market CRUD/UI, live scrapers, integrations, AI analysis, and scoring are not enabled. Collector code exists as an offline-tested shared service, but a real approved source policy and persistence adapter are mandatory before worker or API composition.
- Live checkpoint status: [`progress.txt`](progress.txt). The existing Phase 0 ZIP is a historical snapshot, not the live tracker.
