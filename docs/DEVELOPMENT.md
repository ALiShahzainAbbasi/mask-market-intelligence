# Development — Windows-native processes

This is a modular infrastructure/identity scaffold, not a market-research MVP. Local-auth code and migration are written but deliberately not registered before live database acceptance; market workflows, collectors, AI, and scoring remain incomplete. See [AUTHORIZATION.md](AUTHORIZATION.md) for the identity boundary.

The user removed the container-runtime requirement and then made Windows the required operating platform. [ADR 0002](decisions/0002-container-free-development.md) removes containers; [ADR 0003](decisions/0003-windows-first-lean-runtime.md) establishes a PostgreSQL-backed native Windows worker and local authentication. There is no Docker, WSL, Linux, VM, Redis, or Celery setup step.

## Prerequisites

- Windows 10/11 with Node 24.19.0, pnpm 11.19.0, Python 3.12.13, uv 0.12.9, and Git.
- For live backend features: one separately provisioned native PostgreSQL 17 instance with pgvector (baseline 0.8.2). Record actual approved native versions before acceptance.
- The same Python environment runs the PostgreSQL-backed worker directly on Windows. No separate broker is required.

No command here installs system software, creates a cloud account, starts database services, or grants database privileges. Use an approved PostgreSQL/pgvector Windows installation and preserve integrity checks. No paid service is required for local setup.

## First setup and local preview

From the project root:

```text
pnpm install --frozen-lockfile
uv sync --frozen
pnpm run setup
```

Setup creates an ignored .env once with random local-only values, never prints them, and leaves an existing file unchanged. It does NOT provision the matching database roles/passwords. Update service URLs privately to match your approved instance before migrations/integration; generated strings alone do not configure a database.

Start separate terminals in the project root:

```text
# Terminal 1: native FastAPI, loopback port 8000
pnpm dev:api

# Terminal 2: native Next.js, loopback port 3000
pnpm dev
```

The web and API can start without the database or worker. Liveness should work; readiness must report unavailable until PostgreSQL, migration 0004, and a current worker heartbeat are ready. This is a useful infrastructure preview, not proof that research workflows or jobs work. The API command disables raw HTTP access logs; request middleware emits safe correlation-aware events.

For full local acceptance, provision isolated PostgreSQL/pgvector and roles, configure .env, apply `pnpm migrate`, then start `pnpm dev:worker`, `pnpm dev:api`, and `pnpm dev` in separate Windows terminals. Run `pnpm check:services` and `pnpm test:integration`. The worker claims one PostgreSQL job at a time and Ctrl+C stops new claims before recording a clean worker stop.

Stop ONLY processes you started using Ctrl+C in their own terminals. There is no broad `down`/kill/reset command. PostgreSQL lifecycle is owned by its Windows service/installer; do not stop a shared service or delete databases to clean up the app.

## Commands

| Command | Purpose |
| --- | --- |
| pnpm dev / pnpm dev:web | Web only, 127.0.0.1:3000 |
| pnpm dev:api | API only, 127.0.0.1:8000; no automatic migration |
| pnpm dev:worker | Native PostgreSQL queue worker; one process/concurrency 1 by default |
| pnpm bootstrap:owner -- --organization "MASK AI" --name "Owner" --email "owner@example.com" | Interactive one-time owner bootstrap after migration 0004; password is prompted twice |
| pnpm check:services | Check PostgreSQL/vector/schema, API, and PostgreSQL worker heartbeat |
| pnpm test:unit | Python non-integration plus web tests |
| pnpm test:integration | Fail if services/configuration are missing, otherwise run all real cases |
| pnpm test | Unit and integration; missing services are not a passing result |
| pnpm lint | Python/web lint/format, architecture boundaries, progress consistency |
| pnpm typecheck | Strict Python/TypeScript checks |
| pnpm build | Local Next.js production build, not deployment |
| pnpm migrate | Upgrade the explicitly configured development database to Alembic head |
| pnpm schemas:generate / pnpm schemas:check | Generate/check OpenAPI and TS declarations |
| pnpm check:secrets | Narrow local guard, not a complete security audit |
| pnpm check:source-secrets | Download a pinned/checksum-verified Windows Gitleaks binary and scan with redaction |
| pnpm check:architecture | Static feature/transport/worker imports and cycles |
| pnpm eval-ai | Explicitly not implemented; exits nonzero |

Make aliases provide dev, api, worker, services, test, lint, typecheck, migrate, and eval-ai. For a production-mode local web preview, run `pnpm build`, then `pnpm --filter @mask/web start`; the existing script binds to loopback and does not deploy anything.

## Environment and services

| Variable | Owner / meaning |
| --- | --- |
| MASK_DATABASE_URL | API/worker/queue restricted mask_app database connection |
| MASK_MIGRATION_DATABASE_URL | Privileged migration tooling only; never needed by web/worker |
| MASK_ENVIRONMENT | development locally; never expose development mode publicly |
| MASK_DEV_TOKEN | Protected infrastructure smoke harness only; never browser-exposed |
| MASK_ENABLE_DEV_ROUTES | Defaults false in settings; local example enables it; forbidden outside local/test |
| MASK_LOG_LEVEL | INFO by default; DEBUG/WARNING/ERROR also allowed |
| MASK_API_BASE_URL | Next.js server-only API origin; default http://127.0.0.1:8000 |
| MASK_TEST_API_URL | Integration API origin; default http://127.0.0.1:8000 |
| MASK_AUTH_SESSION_HOURS | Absolute server-session lifetime; default 8, maximum 168 |
| MASK_AUTH_FAILURE_LIMIT | Known-account failures before lockout; default 5, allowed 3–10 |
| MASK_AUTH_LOCKOUT_SECONDS | Login lockout; default 900, allowed 30–86400 |
| MASK_AUTH_RECENT_MINUTES | Recent-password-authentication window for sensitive admin actions; default 15 |

PostgreSQL uses the explicit URL you configure—there is no automatic port mapping. If the native Windows service uses 5432 rather than the example's historical 5433, deliberately update both database URLs. Backend Settings reads the root .env. Export a non-default MASK_API_BASE_URL in the web process environment; Next.js does not automatically read the backend's root .env. No secrets use NEXT_PUBLIC_ variables.

Old POSTGRES_USER/POSTGRES_DB/POSTGRES_PASSWORD/MASK_DB_PASSWORD entries in an existing .env are no longer bootstrap inputs. They are ignored and were not erased or regenerated. URLs must match actual provisioned roles. Do not paste .env or connection strings into chat/logs.

The database administrator must provision the database, a restricted mask_app login (no superuser/createdb/createrole), a separate migration identity, and the required extension privileges. Remove public CREATE access on the application schema; grant the migration identity necessary schema ownership/creation rights. Migrations grant table access to mask_app and preserve definition-snapshot immutability. For the disposable migration-cycle acceptance test, the isolated test migration identity needs database creation and extension privileges. Never grant those to the API/worker identity or use a production instance for this harness.

Bind local PostgreSQL to loopback and restrict network access. The PostgreSQL job table is durable data and follows the same backup/access policy as application records. Remote application services require separately approved credentials/TLS and access controls; the destructive-capable integration harness intentionally rejects remote targets. Do not weaken that guard to test against a shared or production database.

Readiness connection/read/statement waits use MASK_DEPENDENCY_TIMEOUT_SECONDS (default 2, allowed 1–5). Next's API fetch has a separate six-second timeout. These are operation limits, not guarantees under DNS/OS stalls.

## Migrations and safe integration

Create a revision with `uv run alembic -c apps/api/alembic.ini revision -m "describe change"`. Review SQL, add tests, update DATA_MODEL.md, then apply deliberately with `pnpm migrate`. No create_all or auto-migration runs at startup.

Migration 0001 enables vector and the original smoke table; 0002 adds seven identity/market tables; 0003 replaces the smoke table with generic durable jobs and worker heartbeats; 0004 adds local credentials, hashed sessions, and identity security events. Expected head is centralized in persistence/schema.py. Readiness remains unavailable until that head is installed.

Twenty-four integration cases remain: four infrastructure/connectivity, nine schema, four membership, four durable-queue, and three local-authentication cases. They require a provisioned development environment and explicit `--integration` invocation. Synthetic identity/market/auth data rolls back. Queue cases exercise real idempotency, leases, retry exhaustion, cancellation, and worker heartbeats; auth cases exercise Argon2id login, lockout, hash-only persistence, logout, and atomic rotation. The migration-cycle test creates one unique `mask_it_*` database and removes ONLY that database in `finally`. It never downgrades the configured research database.

The database dependency-failure case uses a real probe through an in-process HTTP test client, temporarily targets an exclusively reserved non-listening loopback port, then restores the real service connection. It does not mock query results, stop the Windows service, or verify a server process restart. Actual service restart/persistence recovery, worker error logs, and graceful shutdown remain separately required operator acceptance in P01-06/P01-10.

## CI and security checks

The hosted quality job uses `windows-latest` and the same pinned tools as local development. `pnpm check:source-secrets` downloads the pinned Windows x64 Gitleaks archive, verifies it against the release SHA-256 manifest before extraction, and scans with redaction. No private service credential or real research data belongs in quality artifacts.

Full live integration is not part of a routine unit-quality pass. For the private MVP it runs locally on the isolated Windows/PostgreSQL setup. The optional integration workflow is manual, main-branch-only, and targets an owner-provisioned self-hosted Windows runner; it never runs untrusted pull-request code with private service credentials.

Synthetic JUnit files under ignored reports/ are retained seven days by the workflow. Unit reports and integration reports are distinct; absence of an integration report is not success. Live Gitleaks execution, Python dependency/host-runtime audit, and live operational acceptance are still unverified. Hosted CI is optional until a remote is approved. Record findings/remediation before production.

## Extending and troubleshooting

Follow [MODULARITY.md](MODULARITY.md), scoped AGENTS.md, and progress.txt. Services/domain rules do not import concrete infrastructure. Routers and workers call services; repositories own SQL and tenant predicates. New routes need backend authorization and regenerated contracts. Update the tracker at every checkpoint.

- Service preflight exit 1: it reports safe up/down labels. Provision/configure missing services or apply reviewed migrations; do not mark integration passed.
- Worker cannot start: verify `.env`, PostgreSQL reachability, the current migration head (0004), and `mask_app` table grants. The worker has no broker dependency.
- Owner bootstrap fails safely: verify migration 0004 and application-role grants. Run it only against the intended empty local installation; a second execution is designed to be denied.
- `/auth/*` returns 404: expected until migration 0004 and live auth acceptance pass and the router is deliberately registered. Do not bypass this guard with development-token identity.
- uv unavailable: install/restore the pinned tool through approved means. Do not bypass security controls. An existing compatible virtual environment may run `python -m uvicorn`, `python -m pytest`, `python -m scripts.check_services`, Ruff, and mypy directly; document that these are not uv/frozen-install verification.
- Port in use: change a specific development port and matching URL together. Never stop unrelated processes.
- Permission errors: keep application and migration identities separate; do not promote mask_app to superuser.
- API ready but smoke job stuck: inspect PostgreSQL job status, lease owner/expiry, worker heartbeat, attempts, and safe error fields. A stale worker heartbeat or expired lease should fail readiness until a running worker recovers the job.

The six removed runtime files have recovery copies outside the project at workspace work/docker-removal-backup-2026-09-03. No .env, database, system installation, Windows PATH entry, or standalone executable was removed.
