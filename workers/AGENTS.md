# Worker module rules

Read the root AGENTS.md and docs/MODULARITY.md first.

- Task entrypoints validate delivery metadata, call a shared feature service, and handle bounded retry/logging.
- No SQLAlchemy models, SQL queries, or duplicated scoring/collection/business rules in task entrypoints.
- Resolve concrete dependencies through feature wiring. Use domain exceptions for retry classification.
- Preserve idempotency, tenant/correlation identifiers, version fields, and explicit total-attempt limits.
- Test services without the job runner; test claim/lease/retry wiring separately,
  and do not substitute in-memory/mocked execution for real PostgreSQL/worker acceptance.
- ADR 0003 requires a native Windows Python worker backed by the durable
  PostgreSQL job table. Do not add Redis, Celery, Linux, WSL, a VM, or a second
  queue path. Keep job handlers independent of the runner and persistence adapter;
  handlers validate typed payloads and call feature services, while the runtime
  alone owns claim, lease heartbeat, retry classification, and completion state.
- Default to one worker and concurrency 1. Never raise concurrency or paid-model
  budgets automatically; preserve source throttles and the limits in COST_CONTROL.md.
