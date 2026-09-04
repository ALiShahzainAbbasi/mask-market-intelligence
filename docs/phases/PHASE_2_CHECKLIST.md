# Phase 2 — Authentication, Market Registry & Research Workspace

Status: active development authorized by the user while live database work is deferred. No Phase 2 master checkpoint is complete. Schema, authorization core, and local credential/session implementation are written and offline-tested; Alembic 0004 and all live database/browser acceptance remain open. No paid identity provider is required.

Read root/scoped AGENTS.md, MODULARITY.md, DATA_MODEL.md, SECURITY.md, and progress.txt before work. Keep all 7 master IDs; the subtasks here are not additional roadmap checkpoints.

## P02-01 — Identity and market schema

- [x] Use the six documented roles and distinguish market stage from status.
- [x] Add organization/user/role and market/definition/hypothesis/research-plan models in owning modules.
- [x] Add explicit model registration and shared persistence primitives.
- [x] Freeze Alembic 0002 without importing mutable application models.
- [x] Add tenant/market composite references, definition uniqueness, optimistic version column, and approval metadata constraints.
- [x] Limit application access to definition snapshots to SELECT/INSERT.
- [x] Verify model/DDL agreement, upgrade/downgrade SQL, and expected Alembic head offline.
- [x] Keep market/authentication HTTP routes unregistered.
- [ ] Execute actual PostgreSQL migration/role/grant/deferred-FK and model-reflection checks.
- [ ] Demonstrate upgrade/downgrade/upgrade in the existing disposable-database harness.
- [ ] Pass cross-tenant and cross-market substitution, snapshot-update rejection, and approval-pair tests against PostgreSQL.

## P02-02 — Authentication and tenant authorization

- [x] Add immutable internal session/membership/actor contracts, typed ports, and injected clock; keep real runtime session/provider adapters absent until implemented.
- [x] Add deny-by-default Phase 2 permission map, explicit acting role, fresh membership/status checks, and sensitive-admin recent-auth guard.
- [x] Add tenant-scoped read-only membership repository with bound parameters and safe errors.
- [x] Verify core with 39 identity unit cases, including all role/permission combinations and session/tenant/failure boundaries; document AUTHORIZATION.md.
- [ ] Execute four real PostgreSQL membership-read/fresh-role/suspension cases; SQL-compilation/mapping mocks are not live authorization acceptance.
- [x] Select local accounts plus PostgreSQL-backed server sessions for the private Windows MVP under ADR 0003; optional OIDC is deferred.
- [x] Add maintained Argon2id credential and hashed-session persistence behind typed identity ports; no handwritten password cryptography or development-token login.
- [x] Implement explicit one-time local owner bootstrap CLI, bounded per-account login lockout, session rotation, logout/expiry/revocation, and CSRF controls.
- [x] Add Alembic 0004 for credential, session, and append-only identity-security-event records; verify frozen metadata/offline reversibility.
- [x] Add a separately testable cookie/CSRF HTTP adapter with generic errors; keep it unregistered until live acceptance.
- [ ] Execute Alembic 0004 and the three real authentication persistence cases; run the one-time bootstrap against an empty isolated database.
- [ ] Resolve tenant membership and roles server-side. Do not trust a submitted organization, role, email, or UUID as authorization.
- [ ] Implement the documented permission matrix, explicit admin bootstrap, and role-change audit trail.
- [ ] Test unauthenticated/expired/invalid identity, cross-tenant substitution, and role denials before enabling market routes.

## P02-03 — Market use cases and API

- [ ] Add domain/application contracts and tenant-scoped repository ports; keep routers free of SQL.
- [ ] Create market + initial definition in one transaction, with an existing same-tenant owner.
- [ ] Add bounded input validation, list/detail/update/archive operations and optimistic concurrency.
- [ ] Create a new immutable definition when comparison boundaries change; keep current fields/pointer consistent.
- [ ] Preserve audit events and safe failure/rollback behavior.

## P02-04 — Registry and creation UI

- [ ] Add feature-owned market components/client/hooks/tests with thin App Router composition.
- [ ] Implement authenticated list/create/detail routes and owner/reviewer assignment.
- [ ] Cover loading, empty, unavailable, validation, forbidden, and stale-version states.

## P02-05 — Empty ten-method workspace

- [ ] Render the ten canonical methods with unknown/missing values, not invented scores.
- [ ] Show current definition, stage/status, evidence gaps and next action without implying research exists.

## P02-06 — Controlled state and audit

- [ ] Expose explicit workflow commands; do not allow generic edits to advance research stages.
- [ ] Store actor/role/reason/time for material transitions; no unapproved gate or scoring logic.
- [ ] Implement research-plan/approval rules and required evidence/configuration references.

## P02-07 — End-to-end acceptance

- [ ] Verify authenticated creation, definition versioning, tenant isolation, permissions, archive, optimistic conflicts, and empty workspace.
- [ ] Run provisioned PostgreSQL migrations/integration, Windows worker checks, browser UI checks, and local Windows release commands; hosted CI is optional until a remote is approved.
- [ ] Resolve outstanding Phase 1 acceptance and update tracker/counts before Phase 2 sign-off.

## Current boundaries

Database foreign keys prevent invalid cross-tenant references; they are not authorization or row-level read isolation. The application database role is trusted infrastructure, not an end-user identity. No private research or real users are seeded. Snapshot immutability, grants, deferred constraints, rollback, and membership-query isolation have offline assertions/test cases but remain unverified until PostgreSQL runs. Internal AuthenticatedActor/AccessGrant values cannot be accepted from callers as proof. No auth or market HTTP route is registered.
