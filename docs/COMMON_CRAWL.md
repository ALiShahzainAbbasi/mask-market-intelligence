# Common Crawl Targeted Retrieval

Status: A17.5 offline implementation; live end-to-end retrieval verified once.

## Purpose and boundary

`mask_api.modules.common_crawl_data` is a **historical/fallback** evidence
source: it retrieves one already-archived copy of a specific, already
source-policy-approved URL from the public [Common Crawl](https://commoncrawl.org/)
corpus, when a live fetch of that URL is unavailable or as a secondary
signal. It is targeted retrieval only:

1. One CDX index query (`index.commoncrawl.org`) for a specific URL --
   never a domain-wide or wildcard crawl.
2. Exactly one HTTP `Range`-fetched WARC record (`data.commoncrawl.org`),
   using the exact filename/offset/length one CDX row names -- **never a
   full WARC file or CDX segment download**. A real fetch was verified to
   return `206 Partial Content` with a byte-exact body matching the
   requested range.
3. Decompression and parsing of that single gzip member into the embedded
   HTTP response it contains.

No credential is needed -- both origins are public -- but the module keeps
the same disabled-by-default, explicit `enabled` + `policy_approved`
posture as every other live-capable adapter in this project.

## Reuse, not a new scraper

Per the owner's explicit instruction to extend the existing collector
rather than build a new unrestricted scraper, this module does not
implement its own HTML parser. `retriever.fetch_resource()` produces a
plain `evidence.contracts.FetchedResource` -- the exact same contract a
live static-HTML fetch produces. `integration.to_parsed_document()` then
calls the *existing* `evidence.collectors.static_html.StaticHtmlCollector
.parse()` unchanged to extract title/text, and stamps the result with
Common Crawl provenance in `metadata["common_crawl"]`.
`integration.to_normalized_document()` calls the existing
`evidence.normalization.normalize_document()` unchanged, using a new
`CollectorKind.COMMON_CRAWL` value added to `evidence.domain` for lineage.
No HTML-extraction or normalization logic is duplicated.

`find_capture()` also reuses `evidence.policy.require_allowed_fetch_url()`
with the *same* `SourcePolicy` a live fetch of that URL would use --
Common Crawl retrieval is only ever an alternate way to fetch a URL a
source policy has already approved, never a way to reach a URL that
policy would otherwise deny.

## Recency and provenance

An archived page's `CommonCrawlProvenance` always carries the original
URL, the CDX collection ID (e.g. `CC-MAIN-2026-34`), the 14-digit capture
timestamp, and the exact WARC filename/offset/length -- everything the
owner's directive requires retained per retrieval. That capture timestamp
is the *archive's* observation date, not "now"; callers presenting
Common Crawl evidence must carry it and apply a recency penalty rather
than presenting archived content (a price, a claim) as current.
`find_capture()` selects the most recent of up to `cdx_lookup_limit`
returned captures, but a Common Crawl capture can still be materially
stale relative to a live fetch.

`find_capture()` returns `None` (not an error) both when the CDX index
has never crawled the URL (a real, verified `404` with a JSON `{"message":
...}` body) and when a query returns zero rows -- a normal, expected
outcome for a URL that simply isn't archived, exactly like any other
`SOURCE_UNAVAILABLE`-shaped result elsewhere in this project.

## WARC parsing detail worth knowing

A WARC record's own `Content-Length` header bounds the embedded HTTP
response; the module truncates to it before splitting headers from body.
Without this truncation, the mandatory trailing WARC record terminator
(`\r\n\r\n`) leaks into the extracted body. This was caught and fixed by
comparing a parsed real record's body length against its own declared
HTTP `Content-Length` during implementation -- see `warc.py`'s tests.

## Test contract

Offline tests build small WARC gzip members with the exact real structure
(verified against one real downloaded record) via a shared pytest fixture,
and a fake transport implementing `CommonCrawlTransport` -- covering CDX
request validation, NDJSON parsing (including the real "no captures" 404
shape), WARC parsing (non-response type, missing headers, malformed status
line, missing content-type, terminator truncation), the retriever's
enabled/policy/source-policy-scope/budget gates, short-range-response
detection, disallowed content-type/status rejection, and the reuse
integration into `ParsedDocument`/`NormalizedDocument`.

A gated live smoke test (`test_live_common_crawl_find_capture_and_fetch_resource`,
gated by `MASK_RUN_LIVE_COMMON_CRAWL_SMOKE=1` and
`MASK_COMMON_CRAWL_POLICY_APPROVED=1`) ran a real CDX lookup and ranged WARC
fetch for `https://example.com/` against `CC-MAIN-2026-34` and passed,
including the full reuse path into a parsed document.

## Not yet done

This module is not wired into `evidence.services.CollectionService` or any
`MethodExecutor` -- it produces correct, reusable output, but retry/circuit-
breaker orchestration and persistence dispatch through the shared
collection service are later work, matching the A12/A13 "calculator built,
not yet wired" precedent.
