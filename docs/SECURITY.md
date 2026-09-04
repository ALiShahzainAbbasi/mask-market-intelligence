# Security and Privacy Specification

Status: Phase 0 baseline requirements

## 1. Data classes

| Class | Examples | Default handling |
| --- | --- | --- |
| Public evidence | Permitted public pages and datasets | Tenant-readable; source retention rules apply |
| Licensed/internal | Purchased data, analyst exports, internal assessments | Restricted to authorized organization roles |
| Confidential research | Interview transcripts, private commercial details, customer lists | Need-to-know access, private storage, minimized processing |
| Secrets | API keys, database credentials, session/bootstrap secrets | Environment injection or approved local secret storage; never database content/logs/Git |

Derived summaries, embeddings, and AI output inherit the highest sensitivity and deletion obligations of their inputs.

## 2. Access control

- Authenticated application; deny by default.
- Organization scope on every request, job, query, object, and cache key.
- Role-based permissions for researcher, reviewer, sales, technical, founder, and admin.
- Separate explicit permissions for evidence export, private transcripts, configuration changes, score approval, overrides, veto exceptions, and final selection.
- Service-to-service identities use least privilege and rotated credentials.
- Administrative and founder actions require recent authentication where supported.

Automated tests must attempt cross-tenant ID substitution, object-store access, queue/job access, and filtered-query leakage.

Phase 2 implementation boundaries and its explicit preliminary permission map are in [AUTHORIZATION.md](AUTHORIZATION.md). The provider-independent core is unit-tested; no real login/session adapter or authenticated business route exists yet. Role gates alone do not authorize a particular resource or replace workflow/audit checks.

## 3. Secrets and environments

- Store secrets only in approved environment/secret-management facilities.
- `.env.example` contains placeholders, never working credentials.
- Separate development, staging, and production credentials and databases.
- Do not place secrets in URLs, source-policy notes, prompts, logs, job payloads, error messages, fixtures, screenshots, or audit events.
- Rotate exposed/suspected credentials and record the incident.

## 4. Encryption and storage

- TLS for any non-loopback web, API, database, object storage, and external provider connections.
- Encryption at rest for database backups and object storage as appropriate to the data class.
- Private object buckets with short-lived authorized access; no public transcript URLs.
- Database backups, restore tests, retention, and environment-specific access.
- Checksums for uploaded and retained evidence to detect corruption and support lineage.

## 5. Upload security

- Allow-list necessary types and enforce size/page/row/text limits.
- Verify actual content type; reject archive/path traversal, macro/active content where unsupported, decompression bombs, and malformed payloads.
- Malware scan or quarantine before parsing.
- Parse in a constrained worker with time/memory limits.
- Sanitize filenames and never use them as storage paths.
- Record uploader, checksum, scan result, authority/rights attestation, and retention class.

## 6. AI and prompt security

- Source material is untrusted data and cannot change system instructions.
- Delimit source text and use strict structured-output schemas.
- Disable unneeded model tools/network access for extraction.
- Minimize/redact personal data before external inference.
- Use provider privacy/retention settings appropriate to the data class.
- Prevent cross-tenant retrieval by filtering before vector search, not after.
- Validate all output and evidence spans; never execute generated content.

## 7. Application and API controls

- Validate inputs with length/range/enum limits.
- Use parameterized ORM/database operations.
- Protect browser mutations against CSRF where the authentication design requires it.
- Apply request and user/organization rate limits to sensitive/expensive endpoints.
- Use safe error responses without stack traces or sensitive payloads.
- Pin/scan dependencies and the approved host OS/deployment runtime; address critical findings before production. Container packaging is not used under ADR 0002.
- Apply secure headers and output encoding; rendered evidence is not trusted HTML.

## 8. Workers and collectors

- Workers accept typed job payloads with organization scope and configuration versions.
- Restrict outbound destinations where practical; collectors access only registered sources.
- Collector credentials are source-scoped and cannot be read by unrelated workers.
- Prevent SSRF through URL validation, DNS/IP controls, redirect policy, and blocked internal/link-local ranges.
- Follow `SCRAPING_POLICY.md`; technical blocking is never treated as authorization to evade controls.

## 9. Audit and monitoring

Audit role/permission changes, source-policy changes, evidence access/export, score approvals/overrides, confidence changes, stage transitions, founder exceptions, configuration activation, deletion, and secret/security administrative events.

Operational monitoring covers authentication anomalies, authorization failures, cross-tenant attempts, unusual exports, upload failures, worker/collector abuse patterns, prompt/schema failures, and sensitive-log detection. Audit records contain identifiers and safe diffs, not full transcripts or secrets.

## 10. Privacy, retention, and deletion

- Minimize participant/customer direct identifiers and use pseudonymous reporting.
- Record interview consent/authority, allowed purpose, access class, and retention.
- Support access correction/deletion obligations where applicable.
- Legal/privacy deletion propagates to raw files, normalized text, embeddings, AI output, and non-required caches; dependent findings are marked unavailable.
- Preserve a minimal non-sensitive audit record of who authorized deletion and why.
- Do not use collected personal data for outreach unless separately authorized and lawful.

## 11. Incident response baseline

1. Contain: disable affected key, collector, account, source, or service.
2. Preserve safe logs/evidence and identify tenant/data scope.
3. Assess exposure and applicable notification duties.
4. Eradicate/root-cause, rotate, patch, and validate.
5. Restore from known-good state and monitor.
6. Document timeline, decisions, impact, and preventive changes.

Named owners, notification paths, and provider contacts are filled in before production.

## 12. Production readiness minimum

- Threat model and data-flow review completed.
- Authentication/RBAC and tenant-isolation tests pass.
- Secrets scanning and dependency/host-runtime scanning active.
- Upload and SSRF controls verified.
- Encrypted production connections verified.
- Backups and restore test complete.
- Log/audit redaction verified.
- Retention/deletion workflows tested.
- Incident runbook assigned.
- No unresolved critical security findings.
