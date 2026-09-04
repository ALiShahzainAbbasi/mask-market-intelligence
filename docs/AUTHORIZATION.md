# Identity and authorization boundaries

Status: P02-02 local credential/session implementation is written and offline-tested. The HTTP adapter exists but is deliberately not registered in the application until Alembic 0004 and the live PostgreSQL authentication cases pass.

## What exists

The identity module owns immutable internal contracts, typed authentication/session/membership ports, IdentityService, LocalAuthenticationService, the Phase 2 permission policy, SQLAlchemy membership/authentication adapters, Argon2id password hashing, opaque session/CSRF token generation, and the one-time local bootstrap service. Alembic 0004 adds `user_credentials`, `server_sessions`, and append-only `identity_security_events`; the expected schema head is 0004.

The authorization service accepts a `SecretStr` opaque session handle. `HashedSessionReader` hashes it and resolves only a trusted server-side `SessionRecord`; the persisted session contains no bearer secret or cached roles. A caller-supplied email, organization, user UUID, role, or development smoke token cannot substitute for this boundary.

Local login normalizes email only as an account locator, performs a dummy Argon2id verification for unknown accounts, returns generic denials, enforces bounded per-account failures/lockout, optionally rehashes outdated parameters, and creates the session plus audit event transactionally. Session and CSRF secrets are independent 256-bit random values; only SHA-256 digests are stored. Rotation revokes the old session without extending its absolute expiry. Logout requires the HttpOnly session cookie plus matching CSRF cookie/header and records revocation. Production cookies are `Secure`; all cookies are `SameSite=Strict` and path-scoped to `/`.

`python -m scripts.bootstrap_owner` is interactive and has no password argument or HTTP equivalent. A PostgreSQL advisory transaction lock and empty-organization check make it one-time. It creates the first active owner with admin, founder, and researcher roles, a hashed credential, and a security event without printing the password.

For each service call, the core checks session lifetime/revocation, loads current membership with the stored organization/user IDs, rechecks expiry after lookup, and rejects mismatched IDs, inactive users/organizations, and empty roles. It then checks the requested tenant, explicit permission, and acting role. Dependency failures deny access with sanitized errors, not stale cached permissions. UTC-aware clocks are injected for deterministic testing.

This follows deny-by-default, per-request authorization, and explicit privilege mapping guidance. Role checks are only one part of authorization; object relationships must also be enforced. See [OWASP authorization guidance](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).

## Phase 2 permission map

These are preliminary role gates for market metadata and workspace administration, derived from PRODUCT.md. They do not implement these operations or grant access to private evidence.

| Permission | Acting role allowed |
| --- | --- |
| market.read | researcher, reviewer, sales, technical, founder, admin |
| market.create | researcher |
| market.update | researcher |
| market.archive | researcher |
| research_plan.draft | researcher |
| research_plan.approve | reviewer |
| membership.manage | admin, with recent authentication |

Roles may be combined, but each operation names one acting role that the member actually holds. Admin and founder are not wildcard superusers. For example, an admin who creates research needs the researcher role too. Unknown permissions are denied. Evidence exports, private transcripts, score review/overrides, source/configuration activation, M9, sales validation, vetoes, and final selection need separate explicit permissions and resource policies in their owning checkpoints; market.read does not authorize them.

Permission approval is not workflow approval. P02-03/P02-06 must still check the persisted target tenant, ownership/assignment rules, current definition/version, permitted state, required references, and audit event in the mutation's transaction. Archiving is a status action, not rejection/selection or stage advancement. The policy does not impose researcher/reviewer separation unconditionally; the organization's chosen policy belongs in the later workflow check.

## Internal interfaces and trust

- SessionRecord contains server-side session ID, tenant/user IDs, authentication/creation/expiry/revocation times; no bearer secret or cached role list. Times must be aware and ordered.
- MembershipReader.get(organization_id, user_id) returns current status and roles, not ORM entities, email, or credentials. The SQL adapter uses one statement with tenant/user predicates and a tenant-scoped role join. Missing members return None; no-role members remain unprivileged.
- IdentityService.authenticate resolves request-local actor context. IdentityService.authorize additionally applies tenant and explicit acting-role/permission checks and returns an AccessGrant.
- AuthenticatedActor and AccessGrant are internal values, **not cryptographic credentials** or request DTOs. Never deserialize them from a browser, trust their presence in a job payload, cache them across requests, or use them as substitutes for actual service checks.
- Membership changes and resource mutations must address transaction consistency when implemented. A fresh read does not prevent a later concurrent role change or prove row-level database isolation. This slice does not provide RLS.
- Sensitive admin grants enforce a positive injected recent-authentication window, using the last verified credential authentication time, not session creation/refresh time. Five minutes is a synthetic test setting, not a production default. Runtime policy/configuration remains to be set during session integration.

Feature services do not import repositories, HTTP libraries, settings, or network clients. `wiring.py` composes the concrete adapters at the edge. `auth_router.py` is separately testable but `main.py` does not register it yet, so no login or authenticated business endpoint is exposed before live persistence acceptance.

## Required before enabling login or market endpoints

1. Execute and inspect Alembic 0004 on the isolated PostgreSQL instance, including restricted-role grants, hash constraints, session rotation uniqueness, rollback, and persistence recovery.
2. Run the interactive owner bootstrap once on the empty local installation, verify a second attempt is denied, and privately retain the owner credentials.
3. Pass the three local-auth PostgreSQL cases plus the existing membership cases. Inspect security events and prove raw session/CSRF tokens never persist or appear in logs.
4. Add audited membership/role-change commands; current security events cover bootstrap and session activity, not later role administration.
5. Register the auth router, verify browser cookie/CSRF behavior on loopback, then add resource-level market authorization/transaction tests. Only after this may market routes be registered.

## Verification boundaries

Unit tests cover the full Phase 2 role map plus password hashing, opaque tokens, normalized login, unknown-account dummy verification, inactive/locked/raced accounts, password rehash, session issuance/expiry/rotation/revocation, CSRF, safe HTTP cookies/errors, bootstrap normalization/denials, strict configuration bounds, and repository query scoping.

Repository unit tests inspect PostgreSQL-compiled parameterized predicates and synthetic result mapping. Four membership and three authentication PostgreSQL cases verify tenant-filtered roles/status plus real credential lockout, hash-only session persistence, logout, and atomic rotation using the restricted application role and rolled-back synthetic records. **Those seven cases have not run on this host.** Bootstrap on an empty database and browser registration are separate operator acceptance.
