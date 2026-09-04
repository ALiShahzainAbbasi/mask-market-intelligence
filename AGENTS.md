# AGENTS.md

## Project

MASK AI Market Intelligence & Selection System.

## Source of truth

Read `progress.txt` at the start of every project work session, then read `docs/` before major changes. If code and documentation disagree, stop and resolve the discrepancy. Record material architecture or methodology changes in the relevant document.

## Checkpoint tracking (required)

- `progress.txt` is the canonical execution tracker. Use its stable phase/checkpoint IDs.
- Before implementation, check dependencies and mark the active checkpoint in progress.
- Update the file immediately after every checkpoint attempt or completion, and before ending a session; do not wait until an entire phase is finished.
- Record work done, changed files, exact verification results (including checks not run), limitations/blockers, approvals, and the next resumable action in its append-only history.
- Mark a checkpoint done only after its acceptance checks pass. Never equate drafted documentation, untested code, or missing approvals with implementation completion.
- Recalculate completed/remaining counts and phase rollups; keep the current/next checkpoint, README status, and detailed phase checklists consistent.
- Preserve prior history and stable IDs. Record scope/count changes explicitly. Checkpoint percentages are not estimates of effort or delivery time.

## Architecture

- Next.js + TypeScript web application.
- FastAPI + Python backend.
- PostgreSQL + pgvector persistence.
- PostgreSQL-backed durable worker queue for collection and AI jobs; one native
  Windows Python worker with concurrency 1 by default.
- Alembic for every database schema change.
- Windows-first, container-free operation is required by D12/D13 and ADRs 0002/0003. Do not reintroduce Docker, Compose, WSL, Linux/VM runtime requirements, Redis, Celery, or container-based CI/services. Use direct native Windows web/API/worker commands and PostgreSQL/pgvector. The PostgreSQL queue is the only queue path; keep its domain/contracts, port, SQL adapter, worker runtime, and feature handlers independently testable.

## Lean private-MVP scope (required)

- Read [docs/COST_CONTROL.md](docs/COST_CONTROL.md) before collection, AI, embedding, or orchestration work.
- Build only requirements in the supplied guide and current canonical docs. Do not add speculative automation, cloud infrastructure, microservices, multi-agent workflows, or scale features.
- Paid model usage defaults to disabled. Every enabled run needs hard request, token, document, duration, and owner-approved currency limits; stop before exceeding them and retain partial results honestly.
- Deduplicate and filter deterministically before model calls; process bounded relevant excerpts; cache valid versioned results; never auto-upgrade to a costlier model.
- The first real pilot is 3 markets by default and never more than the guide's 5 without a recorded decision. Begin with 2 permitted collectors.
- Keep local application authentication and PostgreSQL-backed server sessions sufficient for the private Windows installation. OIDC, email delivery, and hosted deployment are optional later integrations, not MVP blockers.

## Modularity (required for every phase)

- Read [docs/MODULARITY.md](docs/MODULARITY.md) before structural changes, and follow scoped AGENTS.md files under apps/ and workers/.
- Use a modular monolith organized by feature ownership. Do not create microservices, generic frameworks, or empty layers without a concrete need.
- Keep composition roots thin: main.py wires the application; routers validate/authorize/translate HTTP; services coordinate use cases; repositories own SQL; domain rules and contracts do not import transport or infrastructure.
- Make external dependencies explicit and injectable through narrow typed interfaces. Do not hide database, queue, network, clock, or authentication access inside business rules.
- Each feature owns its contracts, services, persistence, and tests. Cross-feature access uses documented public contracts/services, never another feature's ORM internals.
- Reuse shared code only when it represents a genuine shared concept. Do not turn utils.py, services.py, models.py, or packages/shared into unrelated catch-all modules.
- Keep web routes thin, organize product UI by feature, and preserve server/client boundaries. Scoring and authorization remain backend responsibilities.
- Workers are adapters: validate delivery metadata and call shared application services; do not duplicate domain logic.
- Add architecture-boundary tests, preserve public behavior during refactors, and run unit tests, lint, types, and contract checks before recording completion.
- Prefer cohesive small files; split mixed responsibilities rather than chasing a line-count target. Document justified boundary exceptions and a migration path.

## Non-negotiable research and safety rules

- Preserve raw evidence and its source context.
- Every score must be traceable to evidence.
- LLMs may classify, extract, summarize, and name clusters; they must not calculate methodology scores, market scores, rankings, confidence scores, or gate decisions.
- Deterministic backend code owns normalization, weighting, scoring, confidence, completeness checks, rankings, and stage gates.
- Keep computed scores, reviewed scores, and confidence separate.
- A reviewed override requires a reviewer, rationale, linked evidence, and timestamp.
- Do not change methodology weights without updating `docs/SCORING.md` and versioning the scoring configuration.
- Do not add collection that bypasses authentication, CAPTCHAs, paywalls, robots controls, or other access restrictions.
- Never commit secrets.

## Quality bar

- Keep tasks small and scoped.
- Add migrations for schema changes.
- Add unit tests for every scoring function.
- Add parser fixtures for every collector.
- Add labelled evaluation fixtures for AI extraction changes.
- Run tests, linting, and type checking before completion.
- Update documentation when behavior or architecture changes.

## Definition of done

Implementation complete; relevant tests, lint, and type checks pass; migrations and documentation are included where needed; errors and logging are handled; no credentials are committed; acceptance criteria are demonstrated; `progress.txt` is updated with checkpoint status, verification, remaining work, and next action.
