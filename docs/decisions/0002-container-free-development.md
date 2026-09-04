# ADR 0002 — Container-free development and verification

Status: adopted under the user's explicit request, "remove docker we will not use anymore".
Date: 2026-09-03. Supersedes only the container/runtime portions of ADR 0001. ADR 0003 later supersedes this decision's Redis/Celery/Linux and external-runner assumptions while retaining the no-container rule.

## Decision

- Remove Docker/Compose from active project files, commands, CI, and integration tests. Do not substitute another container runtime.
- Run Next.js and FastAPI as separate native processes on Windows or Linux. Commands bind to loopback and do not auto-migrate databases.
- Keep PostgreSQL 17/pgvector, Redis, SQLAlchemy/Alembic, and Celery. Removing packaging does not authorize replacing the database, changing queue guarantees, introducing SQLite/fake services, or selecting a paid provider.
- Run the existing Celery worker natively on a supported Linux environment. The worker entrypoint rejects native Windows before loading credentials. A Windows-native queue replacement is a separate architecture decision, not part of this removal. See the [Celery Windows support policy](https://docs.celeryq.dev/en/stable/faq.html#does-celery-support-windows).
- Provision database/Redis services separately with approved installers or an approved host. No service/account is provisioned by this change. Record versions and secure configuration before live acceptance. See the [native pgvector installation instructions](https://github.com/pgvector/pgvector#installation).
- Preserve the existing ignored .env; setup never overwrites it or creates database roles. Old bootstrap-only variables may remain harmlessly ignored until the owner deliberately cleans them up.

## Verification and CI

The service preflight validates local development targets and probes PostgreSQL/vector/schema, Redis, API readiness, and worker responsiveness without leaking connection strings. It fails nonzero when prerequisites are missing. Real integration tests remain separate and required.

The two automated dependency-failure tests now redirect only their own in-process application's connection setting to an exclusively reserved non-listening loopback socket, then restore it. They execute real probes; they never stop shared services. This is application connectivity/recovery acceptance, not evidence of server restart, persistence recovery, or worker shutdown. Those operational checks remain open in P01-06/P01-10.

Hosted quality CI uses native tools and a pinned-version Gitleaks release checked against its published checksum manifest. It does not need a container runtime. Live integration is a separate manual main-branch-only job on an owner-provisioned isolated Linux runner protected by an integration environment. Neither hosted execution nor a runner/account/approval policy is claimed to exist.

## Tracking and recovery

Keep all 151 checkpoint IDs. Rescope P01-07 to native startup/configuration; keep live acceptance incomplete. D10 now means provisioned services and a supported worker environment, not a Docker installation. D11 identity-provider choice is unchanged. D12 records this user-approved change.

Six obsolete project files were removed with recovery copies under the workspace's work/docker-removal-backup-2026-09-03 directory. System software, Windows PATH, standalone work/docker-compose.exe, databases, and data volumes were not modified. Prior tracker history and ADR 0001 retain historical results; they are not current setup instructions.
