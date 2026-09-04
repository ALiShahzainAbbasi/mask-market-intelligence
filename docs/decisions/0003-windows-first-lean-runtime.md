# ADR 0003 — Windows-first lean private runtime

Status: adopted under the user's explicit Windows-only, requirements-only, cost-conscious direction.
Date: 2026-09-03. Supersedes ADR 0001 and ADR 0002 where they require Redis, Celery, Linux, hosted CI, or an external identity provider for the initial private installation.

## Context

The supplied development guide permits Redis/Celery **or an equivalent Python queue**, requires expensive work to run outside API requests, says not to apply expensive AI to every collected item, limits the first real test to 3–5 markets, and explicitly delays broad automation. It requires authentication, role-based access, evidence lineage, deterministic scoring, auditability, and PostgreSQL/pgvector; it does not require a paid identity provider, Linux, hosted deployment, or Redis as the only valid queue implementation.

The product is initially for the owner/team on a Windows system. It must remain useful for real market research without creating infrastructure or model spend that the MVP does not need.

## Decision

- Windows is the required development and initial operating platform. Web, API, database, worker, migrations, tests, and local release checks must all have a documented native Windows path. Do not require Docker, WSL, Linux, or a VM.
- Keep the modular monolith, Next.js, FastAPI, PostgreSQL 17, pgvector, SQLAlchemy, and Alembic.
- Replace Redis/Celery with a durable PostgreSQL-backed Python job queue. This removes one service and the unsupported Windows worker dependency while preserving the guide's `FastAPI -> Queue -> Worker -> Database` boundary.
- PostgreSQL is the queue source of truth. Jobs are transactionally enqueued, claimed with row locking, leased, heartbeated, retried with bounded backoff, recoverable after an abandoned lease, cancellable, observable, and idempotent. `LISTEN/NOTIFY` may reduce polling latency but is only a wake-up optimization; correctness must not depend on notifications.
- Run one native Python worker process by default, with concurrency 1. Scaling or additional worker processes are opt-in only after measured queue demand. Ctrl+C performs a bounded graceful shutdown without accepting new jobs.
- The initial private installation uses local application accounts and PostgreSQL-backed server sessions. Passwords are hashed with a maintained Argon2id implementation; session identifiers are random, rotated, stored hashed, and sent only in HttpOnly/SameSite cookies. State-changing requests require CSRF protection. The owner account is created through an explicit local bootstrap command, never a public endpoint. Password reset/email delivery, social login, and OIDC remain optional later integrations, not MVP blockers.
- Bind web/API/database to loopback by default. Exposing the system to a LAN or Internet is a separate P21 security/deployment decision and requires TLS, a reviewed identity boundary, backups, rate limits, and operational controls.
- Hosted CI, cloud deployment, managed Redis, and paid provider accounts are not required for the private Windows MVP. Local Windows release checks remain mandatory. A future remote may add CI without changing product behavior.

## Queue acceptance contract

The replacement is not accepted until tests demonstrate:

1. API enqueue commits a durable job and returns its identifier without performing long work.
2. A Windows worker claims each job atomically; concurrent workers cannot own the same active lease.
3. Duplicate idempotency keys do not produce duplicate persisted outputs.
4. Retryable failures use capped attempts/backoff; permanent failures and exhausted jobs are explicit.
5. An expired lease is safely reclaimed after a worker crash, while a live heartbeat is not stolen.
6. Progress, safe errors, correlation IDs, configuration versions, and output references remain observable.
7. Ctrl+C stops new claims and gives the current bounded operation a defined shutdown window.
8. Database unavailability fails safely and recovery is demonstrated against an isolated local instance.

The PostgreSQL queue is the only active queue path. Its generic queue adapter and worker runtime remain separate from feature handlers so new research jobs do not duplicate claim, lease, retry, or persistence logic.

## Lean research contract

The mandatory cost and scope controls live in [COST_CONTROL.md](../COST_CONTROL.md). The default is zero paid-provider budget until the owner explicitly configures a non-zero cap. Manual imports, deterministic preprocessing, deduplication, evidence review, and scoring remain usable without paid model calls. Any AI-enabled run must stop at its request/token/currency limits and preserve partial results.

This decision does not change the ten methods, approved overall weights, evidence lineage, deterministic scoring ownership, confidence separation, human review, collector policy, or audit requirements.
