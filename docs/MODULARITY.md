# Modular implementation contract

Status: adopted under the user's request to make the code highly modular.

The system remains one deployable API/worker codebase and one web application. Modules are code boundaries, not new network services. Feature ownership follows ARCHITECTURE.md.

The native runtime decisions are recorded in [ADR 0002](decisions/0002-container-free-development.md) and [ADR 0003](decisions/0003-windows-first-lean-runtime.md). Packaging must not leak into domain rules: web/API/worker run directly on Windows, service readiness is checked through adapters, and workers call shared use cases. PostgreSQL queue mechanics remain an infrastructure adapter, never feature policy.

## Dependency direction

```text
composition / dependency wiring
  -> HTTP or worker adapters -> feature services -> typed ports / domain contracts
  -> persistence / queue adapters ----------------> typed ports / domain contracts
```

Pure domain rules and ports do not know FastAPI, SQLAlchemy, PostgreSQL locking/notification mechanics, environment settings, or network clients. Concrete adapters are wired at the edge, not constructed in a use case. Transactions have an explicit owner. Durable business jobs use the job repository/outbox lifecycle defined by ADR 0003; feature services do not issue claim SQL.

## Backend ownership

- main.py: application composition only.
- transport/: shared HTTP middleware and safe exception handling; no feature queries.
- modules/health/: public readiness/liveness contracts and HTTP adapter.
- modules/smoke/: infrastructure smoke contracts, ports, service, queue adapter, routing, and wiring.
- modules/identity/: organization/user/role/authentication models, explicit permission policy, internal identity/auth contracts and ports, authorization and local-auth services, Argon2id/token adapters, transactional repositories, inactive HTTP adapter, and bootstrap composition. The HTTP adapter remains outside main.py until live acceptance; see AUTHORIZATION.md.
- modules/markets/: market definition/hypothesis/research-plan vocabulary and persistence; services and HTTP adapters are added only as their checkpoints begin.
- modules/evidence/: immutable source-policy and document contracts, pure policy/text/persona normalization and source-family dedupe rules, source parsers, a typed collection service, and explicit HTTP/persistence boundaries. Source parsers consume fetched bytes and never open sockets or write storage; the HTTP adapter and future PostgreSQL adapters stay at the edge. See COLLECTORS.md and the module-scoped AGENTS.md.
- modules/discovery/: pure bounded method-aware query planning plus optional search-provider edge adapters. Provider credentials, policy approval, transport, cost, and response parsing stay outside query generation; discovered URLs are candidates, not approved evidence.
- modules/official_data/: validated fixed-scope request builders, pure fixture-backed parsers, source-neutral observations/records, and a separately injected bounded official-API transport. Credentials are isolated from stored provenance; scoring and persistence remain outside the adapter.
- modules/search_intent/: credential-free search-metrics contracts, pure versioned intent taxonomy, Google Ads request/response mapping, cache port/local artifact adapter, and a fail-closed injected provider edge. Credentials and customer identity stay in a future transport; M6 calculation stays in scoring.
- modules/analysis/: provider-neutral versioned extraction contracts, strict schema registry, analysis cache port/local artifact adapter, disabled injected model-provider edges, and a pure grounding gate with an independent high-impact-verifier port. Provider code maps requests and validates envelopes only; grounding exposes scoring input only after deterministic checks/review, and all methodology math stays in scoring. `workflow-step-v1` is its ninth versioned extraction schema, added for A13.
- modules/pain_intelligence/: A10-accepted pain ingestion, exact/near dedupe, versioned embedding port/cache and zero-cost local hashing adapter, deterministic persona-separated clustering, formula-driven M2 calculation, and report contracts. It owns orchestration but no collection, provider transport, SQL, HTTP, UI, or LLM scoring.
- modules/workflow_intelligence/: A10-accepted workflow-step ingestion, exact grouping by normalized step-name hash (steps have a natural identity, unlike free-text pain mentions, so no embedding/clustering is needed), formula-driven M3 bottleneck calculation, and report contracts. Same orchestration-only boundary as pain_intelligence.
- modules/method_metrics/: typed, source-grounded metric/provenance contracts and the exact formula-v1 M1/M4/M5/M6/M7/M9 source-to-metric transforms and calculators. It turns already-normalized values from official_data/search_intent/a capability registry/integration discovery/manual or leadership capture into scores; it does not fetch, discover, or persist evidence, and it never renormalizes a weighted sum around a missing component.
- modules/confidence/: the v1 confidence aggregation formula, completeness (Proven/Weak/Missing/Not-applicable) classification, and automatic detection of the three purely-numeric v1 vetoes. It consumes method calculators' public result contracts (never their internals) and never computes a method score; it does not derive the four confidence dimensions still pending owner approval (D04), and it honestly reports the three vetoes it cannot yet evaluate rather than guessing.
- modules/market_scoring/: the top of the calculation stack -- the v1 automated research score (never the approved final score), cross-method confidence aggregation, gate readiness evaluation, and the immutable market score snapshot. It composes `confidence`'s and the method calculators' public results and never recomputes a method score, confidence dimension, or veto trigger itself; it never assigns an actual stage transition, only eligibility.
- modules/scoring/: deterministic, version-independent numeric primitives and later formula/gate evaluators. It must not import collectors, AI providers, HTTP, SQLAlchemy, or presentation code.
- research_runner/: strict versioned configuration contracts and the CLI application boundary. The future runner coordinates public module ports; it does not duplicate source, persistence, extraction, scoring, or report rules.
- job_queue/: generic domain/contracts, queue port, SQLAlchemy model/repository adapter, and composition wiring. Feature services depend only on the port; feature handlers and services never import its model/repository.
- config.py, database.py, and health.py: single-purpose infrastructure adapters. Keep settings, connection factories, readiness probes, and queue mechanics out of feature policy.
- persistence/: metadata registration and schema revision, isolated from request handlers.

Within a feature, use only layers that have real work. For example, the still-schema-only markets module needs domain.py and models.py; do not invent empty services/repositories. Identity now has tested use cases and a membership query, so it owns corresponding ports/service/repository files. A shared Base or timestamp mixin may be reused; do not introduce a generic CRUD repository that hides tenant filtering or transactions.

Legacy top-level contracts.py, models.py, and jobs.py may retain explicit compatibility exports while consumers migrate. These are forwarding interfaces, not places for new implementations. Alembic metadata imports all models through a dedicated registry. Historical migrations are self-contained and must not import mutable application models.

## Public module interfaces

Feature contracts/domain values and intentionally named service interfaces are public. Repositories and ORM classes are private implementation details. Cross-feature references in persistence use named foreign keys rather than importing another feature's model. Tenant references include organization identity, and a child definition must belong to the same market. Neither a UUID nor a role name supplied by a caller proves authorization.

Business services receive authenticated tenant/actor context from the authentication boundary. No market HTTP routes are registered until authentication and tenant checks are implemented. Phase 2's schema can be reviewed/tested independently while Phase 1 infrastructure acceptance is outstanding, as explicitly requested by the user; this does not waive any acceptance requirement.

## Frontend ownership

Keep src/app for route composition/layout/loading/error boundaries. Put product-specific components, hooks, validated clients, and tests under src/features/<feature> as product screens are introduced. Keep components/ui presentation-only and lib limited to genuinely shared helpers. The existing health-only page is already small and does not need a speculative feature hierarchy.

Server Components own server-only API/session access. Client Components own interaction and receive explicit serializable view data, not ORM objects or credentials. Use generated API contracts plus runtime validation at remote-data boundaries. Frontend visibility is not authorization. No methodology scoring logic belongs in UI components.

## Worker ownership

Workers obtain a claimed typed envelope through queue wiring, call feature services, and emit safe correlation-aware logs. The PostgreSQL queue adapter owns claim/lease/heartbeat SQL; feature repositories own business state and idempotent output. The runner and handlers must not import ORM models, issue SQL directly, or duplicate API use cases.

The CLI may explicitly select a `LocalArtifactStore` adapter through the same typed persistence boundary used by the research use case. That adapter is a named execution target, never an automatic fallback when PostgreSQL or API wiring fails.

## Verification and change checklist

1. Name the owning module and its public boundary before adding code.
2. Keep pure logic independent of frameworks and I/O; inject adapters at wiring.
3. Add unit tests at service/domain seams and repository/integration tests for SQL behavior.
4. Run pnpm check:architecture, unit tests, lint, type checks, and contract drift checks.
5. Preserve historical migrations; add new revisions and live migration/tenant-isolation tests.
6. Update architecture/data-model docs and progress.txt after each checkpoint attempt.

The architecture checker enforces Python import boundaries and cycles; it is not proof of runtime authorization, transaction correctness, or PostgreSQL constraints. Those require the separate acceptance suites. Frontend boundaries are enforced through review and existing lint/type checks until product feature modules exist.
