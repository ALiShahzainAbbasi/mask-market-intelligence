# Data Collection and Scraping Policy

Status: Phase 0 canonical policy  
Applies to automated collectors, browser-assisted collection, third-party data, analyst uploads, and manual capture.

## 1. Policy objective

Collect useful market evidence lawfully, ethically, reproducibly, and without bypassing technical or contractual controls. Research value does not override source restrictions, privacy obligations, or data rights.

## 2. Allowed collection paths, in priority order

1. Official API under its documented terms and approved credentials.
2. Licensed/permitted third-party dataset with recorded rights and retention terms.
3. Analyst-supplied export or upload that MASK AI is permitted to process.
4. Straightforward public HTTP collection when the source policy, terms, robots controls, rate limits, and applicable law permit it.
5. Browser rendering only for legitimate public dynamic pages where collection is permitted.
6. Manual evidence capture with source URL, date, analyst, permitted excerpt/context, and policy note.

The narrowest reliable method should be used. Playwright is not a workaround for a blocked HTTP request.

## 3. Prohibited behavior

Collectors must never:

- bypass login, authorization, paywalls, CAPTCHAs, robots controls, rate limits, geofencing, or other access controls;
- use stolen/shared credentials or impersonate a person;
- defeat anti-bot protections, fingerprinting, or technical restrictions;
- collect private groups, messages, accounts, or personal records without explicit authority;
- ignore a source's approved query, field, purpose, or retention restriction;
- scrape more data than the registered research purpose requires;
- continue collection after a source is marked blocked or its approval expires;
- turn a manual-access exception into an automated collector without a new policy review.

If access is prohibited or technically blocked, use an official API, permitted provider, analyst export, or manual evidence workflow. Otherwise do not collect it.

## 4. Source registration is mandatory

Before the first run, every source has an approved policy version recording:

- source name/type and base URL;
- collection method and allowed actions/fields;
- status: `allowed`, `conditional`, `blocked`, or `review_required`;
- terms and robots review dates and reviewer;
- authentication requirements and secret reference (never the secret itself);
- request and concurrency limits;
- allowed query scope and user-agent/contact requirements;
- personal/sensitive data expectations;
- raw-content and derived-data retention;
- attribution/citation requirements;
- policy notes and expiry/review date.

The collector run stores the exact policy version. A missing, expired, blocked, or incompatible policy prevents dispatch.

## 5. Rate limiting and respectful access

- Apply per-source token-bucket or equivalent limits plus a global worker ceiling.
- Default to conservative concurrency; the registered source limit wins.
- Honor server instructions such as `Retry-After` and back off on 429/403/5xx patterns.
- Retries use capped exponential backoff with jitter and never become an unbounded loop.
- Cache permitted responses and deduplicate discovery to avoid repeat requests.
- Schedule large runs off peak when appropriate and approved.
- Identify the client accurately when the source requires a user agent/contact.
- Automatic circuit breakers pause a source after configured policy/error thresholds.

Rate-limit values are source configuration, not hard-coded assumptions. Tests use fixtures or approved sandboxes, not uncontrolled live load.

## 6. Collector implementation standard

Each collector implements the common `discover -> fetch -> parse -> normalize -> persist` contract and declares:

- source and policy compatibility;
- supported query/input contract;
- parser/collector version;
- pagination and stop rules;
- idempotency key construction;
- expected metadata and provenance;
- retryable versus permanent errors;
- rate-limit behavior;
- parser fixtures including malformed/empty cases;
- fields intentionally excluded for policy/privacy.

Collection, parsing, AI analysis, and scoring are separate jobs. A parser failure retains the permitted raw response/reference where policy allows and records the error; it does not fabricate a document.

## 7. Common normalized document contract

At minimum:

```text
source_id
source_policy_version_id
source_url or upload provenance
external_id (when available)
title
author/persona hint (when permitted)
published_at
collected_at
raw content/reference
normalized text
language
content hash
source-specific metadata
access and retention class
collector/parser/normalizer versions
```

Original timestamps, units, and material context must not be removed merely to simplify downstream analysis.

## 8. Deduplication

- Exact duplicates use a versioned normalized-content hash.
- Near duplicates use a versioned embedding model, deterministic similarity threshold, and optional human review.
- Every occurrence keeps provenance, but duplicates do not inflate sample size, frequency, or source agreement.
- Canonicalization never deletes the other source occurrence.

## 9. Relevance and minimization

Run inexpensive deterministic checks and a relevance classifier before costly extraction. Relevance labels are `Relevant`, `Possibly Relevant`, and `Irrelevant`.

Irrelevant documents may be retained only as long as source policy and evaluation/audit needs justify. They are excluded from method analysis by default. Collect only fields required for the registered research purpose; remove or tokenize unnecessary direct identifiers during normalization.

## 10. Uploads and manual evidence

- Validate type, size, checksum, malware/active content, and parser limits before processing.
- Record uploader, rights/authority attestation, origin, and access class.
- Preserve the original in approved private storage when required for lineage.
- Treat private interviews, commercial exports, and customer lists as restricted, not public web evidence.
- Manual captures include who captured what, when, from where, under which policy, and enough context to review the claim.

An upload does not confer rights that the uploader does not have.

## 11. Retention and deletion

Raw evidence should normally be preserved so later analysis remains auditable. Retention is nevertheless bounded by the source license/terms, privacy obligations, research purpose, and organization policy.

- Public permitted evidence: retain according to its registered source policy; prefer storing only the necessary excerpt/content plus stable provenance when full-content retention is restricted.
- Licensed/third-party evidence: follow contract limits and segregate access.
- Interviews/private commercial data: restricted access, explicit retention period, and deletion capability.
- Derived embeddings and AI output inherit the source's access and deletion obligations.
- A legal/privacy deletion tombstones or purges affected content and derived data, records non-sensitive reason/authority, and marks dependent findings/snapshots as having unavailable evidence. It never silently rewrites history.

## 12. Incident and change response

Pause collection when terms, robots rules, technical behavior, or source ownership changes materially; when complaints arrive; or when repeated authorization/policy errors occur. Review the source, update/approve a new policy version, test safely, and only then resume.

Security or privacy incidents follow `SECURITY.md`; operational failures record collector/job errors and do not trigger attempts to evade blocking.

## 13. Collector acceptance checklist

- Approved, current source-policy version.
- No prohibited bypass behavior.
- Common contract and idempotency implemented.
- Rate limiting, retry caps, circuit breaker, and pagination stop rules tested.
- Parser fixtures cover success, empty, malformed, changed-layout, and duplicate cases.
- Provenance, timestamps, and raw/normalized separation verified.
- Privacy/minimization and retention behavior documented.
- Logging contains correlation/error context without credentials or unnecessary sensitive content.
- Live smoke test, if permitted, is deliberately small and recorded.
