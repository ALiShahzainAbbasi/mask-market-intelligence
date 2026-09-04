# Collector implementation

Status: Phase 3 implementation contract; offline collector core implemented,
database and live-source integration pending.

## Current scope

The lean Windows MVP starts with two reusable collectors:

1. `rss_atom` parses permitted RSS 2.x and Atom feeds.
2. `static_html` extracts visible text from explicitly supplied, permitted static
   HTML pages.

They are not platform-specific production sources. No source is collected until
its exact source-policy version is registered, reviewed, approved, current, and
compatible with the requested collector. Tests use local fixtures only. There are
no browser collectors, broad crawlers, paid model calls, or background collection
side effects in this slice.

## Module boundaries

| File/package | Responsibility |
| --- | --- |
| `modules/evidence/domain.py` | Source, collector, access, and run vocabulary |
| `contracts.py` | Immutable typed source policy, raw/parsed/normalized document, duplicate, run, and persistence contracts |
| `ports.py` | Narrow policy lookup, fetch, persistence, clock, sleep, jitter, and cancellation interfaces |
| `policy.py` | Pure dispatch and exact-origin URL rules |
| `collectors/` | Deterministic discovery and parsing of already-fetched bounded bytes |
| `normalization.py` | Versioned NFKC text normalization, hashes, occurrence keys, and exact duplicate links |
| `services.py` | The ordered collection use case, finite retry/backoff, per-source intervals, hard limits, cancellation, circuit breaking, and run result |
| `http_fetcher.py` | Concrete public-HTTP edge adapter with DNS/SSRF, TLS, MIME, size, timeout, redirect, proxy, and cookie controls |
| `wiring.py` | Collector construction only; policy and persistence adapters remain intentionally unwired |

The parsers never access the network or database. The service knows only typed
ports. The eventual Windows worker will validate a claimed job and call this same
service; it must not duplicate collection rules.

## Pipeline and lineage

The service executes:

```text
load immutable policy version
  -> verify approval/reviews/effective dates/method/collector/no-auth compatibility
  -> discover bounded explicit URLs
  -> validate exact origin, path, and query scope
  -> fetch sequentially through the bounded HTTP adapter
  -> retain each permitted raw response, including parser failures
  -> parse source-specific fields
  -> normalize with text-nfkc-v1
  -> hash normalized content and retain every duplicate occurrence
  -> persist one typed collection batch using a deterministic run/policy key
```

The common normalized document carries source and policy IDs, source URL,
external ID, permitted author hint, source and collection timestamps, raw bytes
and checksum, normalized text and content hash, metadata, access/retention class,
and collector/parser/normalizer versions. Raw bytes are excluded from normal error
representations but remain available to the persistence boundary.

## Safety and cost behavior

- Only `allowed` policy versions dispatch. Conditional, blocked, review-required,
  missing, unreviewed, not-yet-effective, and expired policies fail before fetch.
- These collectors are anonymous. A source requiring authentication is rejected;
  it needs a separately reviewed official-API or licensed-data adapter.
- Fetch URLs must match the approved scheme, hostname, effective port, path
  prefixes, and query-name allowlist. Credentials and fragments are rejected.
- Every resolved address must be globally routable. Requests use verified TLS,
  no ambient proxy, no cookie jar, no redirects, and identity content encoding.
- Source-policy values bound discovered URLs, attempts, requests, documents,
  response bytes, total bytes, request time, run time, interval, retry delay, and
  circuit threshold. Work remains sequential even if a source permits more.
- Retryable failures use finite capped exponential backoff with bounded jitter.
  A `Retry-After` longer than the approved cap stops retrying instead of sleeping
  or running indefinitely.
- Scripts, styles, forms, SVG, templates, cookies, and non-lineage response
  headers are intentionally excluded by the generic HTML path. Author capture is
  off unless the approved policy explicitly permits it.

## Not yet enabled

No API route or worker handler constructs this service because Phase 3 database
work was explicitly deferred. Before live use, add and verify the PostgreSQL
source-policy provider and idempotent evidence writer, Alembic evidence schemas,
tenant/market authorization, durable collector job handler, run monitoring, and a
deliberately small source-approved smoke test. Robots and terms are currently
approval records, not an automated permission override; a material change pauses
collection for review.

## Adding a source-specific collector

Implement the `Collector` protocol, use an explicit `CollectorKind`, document its
pagination and stop rules plus excluded fields, and add local fixtures for valid,
empty, malformed, changed, and duplicate inputs. Do not put network, persistence,
AI, scoring, credential workarounds, or policy exceptions in the parser. A real
source still needs a separately approved policy version before dispatch.

Focused offline verification:

```powershell
python -m pytest -p no:cacheprovider apps/api/tests/evidence -q
python -m ruff check apps/api/src/mask_api/modules/evidence apps/api/tests/evidence
python -m mypy apps/api/src/mask_api/modules/evidence
```

