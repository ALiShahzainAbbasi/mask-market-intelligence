# Phase 1 — Native repository and development environment

Status: 5/10 master checkpoints complete; the D13 PostgreSQL queue implementation is offline-verified, while native PostgreSQL/Windows operational acceptance remains. D12/D13 replace earlier runtime assumptions in place without changing checkpoint IDs or counting unverified live work as complete. Historical Phase 1 results remain in progress.txt.

## P01-01 / P01-02 — Decisions and repository

- [x] Pin Node/Python/package managers and application dependencies; preserve lockfiles and the accepted domain stack.
- [x] Keep modular instructions, monorepo structure, generated schemas, ignored secrets, and safe setup.
- [x] Replace startup commands with native web/API commands; the guarded Linux worker was an interim D12 step and is superseded by D13.
- [ ] Replace the Redis/Celery smoke adapter with the PostgreSQL queue and native Windows worker acceptance contract.
- [ ] Verify the complete native bootstrap on a clean Windows environment; record PostgreSQL/pgvector versions.
- [ ] Configure an owner-approved remote and branch protection; local main has no commits/remote yet.

## P01-03 / P01-04 — Web and API foundation

- [x] Next.js strict TypeScript, server-only API boundary, generated contracts, safe status UI, unit/component checks.
- [x] FastAPI settings, structured safe errors/correlation logs, liveness/readiness, SQLAlchemy/Alembic, offline migration checks.
- [x] Preserve 127.0.0.1 development bindings and never expose development smoke tokens in the browser.
- [ ] Re-demonstrate web-to-API readiness against actual provisioned services as part of clean acceptance.

## P01-05 — Database

- [x] Keep feature-owned models, frozen migrations, expected-head checks, and restricted application-role grants.
- [ ] Provision an isolated native PostgreSQL/pgvector development instance with separate application/migration identities.
- [ ] Verify actual extension/vector behavior, 0001/0002 migration/reflection/constraints/grants, and disposable upgrade/downgrade/upgrade.
- [ ] Verify database permissions/network binding, safe persistence, and recovery using the selected service manager.

## P01-06 — PostgreSQL queue and Windows worker (rescoped by D13)

- [x] Keep real delivery acceptance separate from eager/mocked unit tests.
- [x] Preserve typed envelopes, shared use cases, idempotency expectations, retry bounds/time limits, and safe metadata from the interim adapter.
- [x] Add the durable jobs schema and PostgreSQL adapter for enqueue, atomic claim, lease, heartbeat, retry scheduling, cancellation, recovery, and terminal state.
- [x] Replace python -m workers with the native Windows runner; default concurrency 1 and bounded Ctrl+C shutdown.
- [x] Remove Redis/Celery dependencies, settings, readiness fields, worker guard, tests, and workflow references as one verified code migration.
- [ ] Verify API -> PostgreSQL queue -> Windows worker -> database, concurrent claim safety, duplicate safety, retries, correlation/error logs, lease recovery, and graceful shutdown.
- [ ] Demonstrate operator-controlled PostgreSQL restart and persistence recovery on the isolated environment. Automated connection-failure tests are not a replacement for this.

## P01-07 — Native startup and shutdown (rescoped by D12)

- [x] Remove project Docker/Compose runtime files and commands; preserve recovery copies outside the project.
- [x] Define pnpm dev/dev:web, dev:api, dev:worker, check:services, and make aliases.
- [x] Keep .env setup non-overwriting; document that roles/services are provisioned separately.
- [x] Require actual safe local service preflight for integration; do not silently fall back to mocks.
- [ ] Confirm clean Windows provisioning -> reviewed migration -> worker/API/web startup -> healthy preflight.
- [ ] Verify stopping only owned foreground processes with Ctrl+C; do not introduce broad host-service kill/reset commands.

## P01-08 — Quality and CI

- [x] Keep unit/lint/format/types/contracts/architecture/progress checks and synthetic JUnit outputs.
- [x] Replace source scanner with native version-pinned/checksum-verified Gitleaks CLI invocation.
- [x] Define a Windows hosted quality job and a guarded, manual, self-hosted Windows integration job.
- [x] Replace platform-specific scanner/workflow assumptions with pinned Windows-native local release commands and static contract checks.
- [ ] Execute the downloaded Gitleaks scanner and inspect findings/artifacts on the approved Windows environment.
- [ ] Run the complete release suite on Windows. Hosted CI/branch protection is deferred until the owner approves a remote; any future runtime acceptance job must include Windows.
- [ ] Complete Python dependency/host-runtime audit and required remediation before production; prior JS audit is historical.

## P01-09 — Documentation

- [x] Update DEVELOPMENT.md, ADR 0002, README, current tracker, and scoped instructions with native commands and platform boundaries.
- [x] Preserve immutable historical tracker evidence and annotate superseded ADR 0001 packaging.
- [x] Keep database/queue/identity decisions and scoring approvals distinct from runtime packaging.

## P01-10 — Required clean-environment demonstration

After provisioning the explicitly isolated local services and approved runtimes:

```text
pnpm install --frozen-lockfile
uv sync --frozen
pnpm run setup
# Privately set provisioned service URLs; setup does not create accounts.
pnpm migrate
# In separate Windows terminals: pnpm dev:worker, pnpm dev:api, pnpm dev
pnpm check:services
pnpm test
pnpm lint
pnpm typecheck
pnpm schemas:check
```

- [ ] Web shows actual API/readiness, not synthetic research.
- [ ] API liveness/readiness and the updated real PostgreSQL/worker service cases pass.
- [ ] Connection fault -> safe unavailable response -> restored connection passes for PostgreSQL.
- [ ] Operator service restart/persistence recovery and worker log/shutdown checks pass separately.
- [ ] Native Windows local release checks pass; hosted branch checks are required only after a remote is approved.
- [ ] No secrets exposed, no application superuser privileges, and no private research in test artifacts.
- [ ] Update progress.txt with exact results, remaining checks, and checkpoint rollups before phase sign-off.
