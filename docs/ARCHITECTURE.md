# Architecture Specification

Status: Phase 0 canonical specification

## 1. Architecture goals

- Preserve evidence and make every conclusion reversible to source context.
- Keep collection, AI interpretation, deterministic scoring, and human approval as separate concerns.
- Make long-running work asynchronous, observable, retryable, and idempotent.
- Support the same methodology across markets and retain all historical versions.
- Start cost-consciously without preventing later scale.

## 2. Chosen stack

| Layer | Technology | Responsibility |
| --- | --- | --- |
| Web | Next.js App Router, TypeScript, Tailwind, shadcn/ui, TanStack Table/Query, chart library | Research, evidence, review, comparison, and decision UI |
| API | Python, FastAPI, Pydantic, SQLAlchemy, Alembic | Authorization, workflows, domain rules, deterministic calculations, persistence API |
| Database | PostgreSQL + pgvector | Transactional records, evidence, audit, vector similarity |
| Queue | PostgreSQL durable job table + native Python worker | Long-running collection, normalization, embedding, AI, clustering, and recalculation jobs on Windows |
| Worker libraries | Python standard-library HTTP/HTML/XML for the lean test collectors; add httpx, BeautifulSoup, Scrapy, Playwright, pandas, scikit-learn, or an OpenAI SDK only where a permitted source/approved module requires it | Collection and analysis workers |
| Optional orchestration | n8n | Notifications, schedules, CRM/import workflows; never core scoring |

## 3. Runtime topology

```text
Browser
  -> Next.js web
      -> FastAPI API
          -> PostgreSQL + pgvector + durable jobs
               -> native Windows Python worker
                    -> collector handlers
                    -> normalization/dedup handlers
                    -> AI extraction handlers
                    -> embedding/clustering handlers
                    -> deterministic scoring handlers
```

Large collection or LLM work never runs synchronously inside an API request. The API validates permission/input, creates a durable job, and returns a job identifier. Workers checkpoint status and results. The web polls or subscribes to job state.

## 4. Repository shape for Phase 1

```text
mask-market-intelligence/
├── AGENTS.md
├── README.md
├── Makefile
├── .env.example
├── .gitignore
├── apps/
│   ├── web/                 # Next.js application
│   └── api/                 # FastAPI application and migrations
├── workers/
│   ├── collectors/
│   ├── analysis/
│   ├── clustering/
│   └── scoring/
├── packages/
│   ├── schemas/             # language-neutral contracts/generated artifacts
│   └── shared/
├── scripts/
├── tests/
│   ├── fixtures/
│   ├── integration/
│   └── evaluation/
└── docs/
```

Domain code shared by API and Python workers should live in an installable Python package under `apps/api` or a clearly named package rather than being copied into worker directories. TypeScript and Python share API/JSON Schema contracts through generated artifacts, not runtime imports across languages.

## 5. Domain boundaries

| Module | Owns |
| --- | --- |
| Identity & tenancy | Organizations, users, roles, authorization |
| Market registry | Markets, definition versions, hypotheses, stage/status |
| Source governance | Source registrations, policy, credentials references, collection permissions |
| Collection | Collector runs, jobs, raw document creation |
| Evidence | Normalization, exact/near duplicate links, documents, evidence items, review state |
| AI analysis | Analysis runs, prompt/model/schema versions, extracted signals |
| Method intelligence | M1–M10 structured records and aggregates |
| Scoring | Rubrics, configurations, deterministic calculations, confidence, snapshots |
| Review & decisions | Score approvals, overrides, red flags, stage-gate decisions |
| Audit | Append-only events across every material change |

Modules communicate through explicit service interfaces and durable identifiers. The web does not implement business scoring rules.

Runtime packaging follows [ADR 0002](decisions/0002-container-free-development.md), and the Windows-only operating model follows [ADR 0003](decisions/0003-windows-first-lean-runtime.md). Web, API, PostgreSQL/pgvector, and the Python worker run natively on Windows. PostgreSQL is both the record store and durable queue; Redis, Celery, Docker, WSL, Linux, and a VM are not target prerequisites. The queue domain/contracts and port are independent of SQLAlchemy; one SQLAlchemy adapter owns persistence, while feature handlers remain independent of the worker runner.

The executable module boundaries and feature layout are defined in [MODULARITY.md](MODULARITY.md) and scoped AGENTS.md files. Keep composition, transport, use cases, and persistence separate; architecture checks run with the regular quality commands.

## 6. Evidence processing pipeline

```text
Source registration/policy check
  -> discovery/fetch or analyst upload
  -> immutable raw document
  -> normalized document version
  -> exact/near-duplicate decision
  -> relevance extraction + human sampling
  -> methodology-specific AI extraction
  -> reviewed evidence items/pain mentions
  -> deterministic aggregates/clusters
  -> deterministic method calculation
  -> human-reviewed method score
  -> immutable market score snapshot
  -> gate evaluation
  -> human decision
```

Each arrow creates or links a record; it does not overwrite lineage.

## 7. Evidence lineage invariant

The minimum navigable path is:

```text
Market
  -> score snapshot
  -> method score/calculation component
  -> method_score_evidence link
  -> evidence item or structured method record
  -> analysis run (when AI-derived)
  -> normalized document version
  -> raw document
  -> source + source URL or uploaded-file provenance
```

Reverse navigation is required. Cluster aggregates retain membership links to individual mentions; summaries never become the only evidence.

## 8. Job architecture

Every asynchronous job has type, organization/market scope, status, progress, idempotency key, input reference, configuration versions, attempts, timestamps, error code/message, and output references. States are `queued`, `running`, `partial`, `succeeded`, `failed`, and `cancelled`.

- Jobs are inserted in the same PostgreSQL transaction as their initiating state change or through an explicit outbox boundary.
- Workers atomically claim eligible rows with row locks, store an owner and expiring lease, heartbeat bounded work, and safely reclaim abandoned leases.
- Polling is the correctness path. PostgreSQL `LISTEN/NOTIFY` may wake a worker sooner but lost notifications cannot lose work.
- Retries use capped exponential backoff with jitter and source-specific limits.
- Jobs are at-least-once; handlers must be idempotent.
- A deterministic key prevents duplicate persisted output for the same input and version.
- Partial collection retains successfully persisted documents and reports failures.
- Poison inputs are quarantined after the configured attempt limit.
- Logs use correlation IDs but do not include secrets or full private transcripts.

## 9. Collector contract

Conceptual interface:

```python
discover(context) -> candidates
fetch(candidate, policy) -> raw_response
parse(raw_response) -> parsed_document
normalize(parsed_document) -> normalized_document
persist(normalized_document, provenance) -> raw_document_id
```

Collectors return one common contract with source, URL, external ID, author/persona hint, published time, raw text or permitted payload reference, normalized text, language, metadata, and collection provenance. Collectors do not run methodology scoring.

The Phase 3 core lives in the installable `modules/evidence` package so the native
worker can call the same use case as future API composition. Source parsers only
discover and parse; a policy-enforcing HTTP edge adapter fetches bytes, the
application service applies normalization/deduplication and run limits, and a
typed persistence port owns the final transaction. See `COLLECTORS.md`.

Uploads use the same normalization/persistence pipeline and record original filename, checksum, uploader, upload time, access class, and parsing version.

## 10. Deduplication and vector use

- Canonicalize text with a versioned normalization algorithm.
- Exact duplicates share a normalized content hash and produce a duplicate link; retain provenance for each occurrence.
- Near-duplicate detection uses embeddings plus deterministic thresholds and, where needed, human review.
- Near duplicates are excluded from frequency/sample inflation without deleting them.
- Embeddings store provider/model/dimensions/version and are regenerated as a new version rather than overwritten.
- pgvector supports similarity retrieval and cluster preparation; deterministic code selects thresholds and clustering parameters.

## 11. API and web contracts

- Version API routes and structured schemas.
- Use Pydantic as the backend validation authority and generate OpenAPI.
- Use organization scoping on every query and mutation.
- Use optimistic concurrency/version fields for reviewable records.
- Mutations that approve, override, gate, or transition state are explicit endpoints, never implicit side effects of reads.
- Large evidence bodies are paginated and access-controlled.

## 12. Scoring architecture

Scoring consumes approved structured inputs and a versioned configuration. Pure functions produce component values, final method contributions, confidence, completeness, and gate eligibility. They make no network calls and do not invoke an LLM.

The calculation output stores its input IDs/hash and a machine-readable breakdown. A score is recalculated by creating a new snapshot; historical snapshots remain immutable. See `SCORING.md`.

## 13. Human review architecture

AI output begins in `proposed`. Authorized users can accept, correct, reject, or supersede it. Review actions are append-only events. Score approval and stage decisions identify the user, acting role, evidence set, configuration, and timestamp.

Critical vetoes never cause automatic rejection; they block automatic eligibility and require a recorded human decision.

## 14. Initial operation and later deployment

The initial private MVP is one Windows installation: loopback web/API, native PostgreSQL/pgvector, and one native Python worker with concurrency 1. Use the local filesystem adapter for approved private uploads until volume or backup requirements justify object storage. Local authentication and PostgreSQL-backed sessions avoid a mandatory identity-provider account.

Internet or team-hosted deployment is deferred to P21. It may use approved managed web/API/PostgreSQL/object-storage services, but it does not add Redis or change queue/domain contracts. Production services require encrypted connections, private credentials, backups, health checks, and separate environments.

## 15. Observability

- Structured logs with request/job/organization correlation IDs.
- Metrics for API latency/errors, queue age, job success/partial/failure, source throttling, documents processed, duplicate/relevance rates, AI cost/latency/schema failures, and scoring reproducibility.
- Alerts for stuck queues, repeated collector failures, database capacity, policy violations, and evaluation regressions.
- Audit events are business records, not substitutes for operational logs.

## 16. Architecture decisions and remaining deferred choices

- Supported runtime and dependency versions are pinned in manifests/lockfiles.
- The PostgreSQL-backed queue and local account/session implementations follow ADR 0003 and their feature ports; live operational acceptance remains open.
- Optional OIDC remains deferred behind the identity ports.
- Object-storage provider.
- Monorepo package manager and task runner.

The current choices and supersession chain are recorded in ADRs 0001–0003. Local operation is documented in [DEVELOPMENT.md](DEVELOPMENT.md), and mandatory spend/scope limits are in [COST_CONTROL.md](COST_CONTROL.md). Provider accounts/deployment and numerical scoring proposals remain deferred; the non-negotiable evidence and scoring boundaries are unchanged.
