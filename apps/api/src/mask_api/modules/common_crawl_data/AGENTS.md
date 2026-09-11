# Common Crawl data module rules

Read the root `AGENTS.md`, `progress.txt`, `docs/COLLECTORS.md`,
`docs/SCRAPING_POLICY.md`, and `docs/MODULARITY.md` before changing this
module.

- This is **targeted retrieval only**: one CDX index lookup, then exactly
  one HTTP `Range`-fetched WARC record. Never download a full WARC file or
  a full CDX segment. `CommonCrawlTransport.fetch_warc_range` must always
  send an explicit `Range` header and the caller must always pass an exact
  `length` derived from a real CDX capture row -- never an open-ended fetch.
- Common Crawl is a **historical/fallback** source. `warc.py`'s parsed
  `warc_date`/the capture's `timestamp` is the observation date of the
  archived copy, not "now" -- callers presenting Common Crawl evidence must
  carry that date and apply a recency penalty; never let archived content
  read as current without it. `CommonCrawlProvenance` exists specifically so
  that date and the exact WARC filename/offset/length are never dropped.
- Reuse, don't duplicate: `integration.py` turns a retrieval into a
  `ParsedDocument`/`NormalizedDocument` by calling the *existing*
  `evidence.collectors.static_html.StaticHtmlCollector.parse()` and
  `evidence.normalization.normalize_document()` unchanged. If HTML
  extraction ever needs to change, change it there, not here.
- `find_capture()` calls `evidence.policy.require_allowed_fetch_url()` with
  the same `SourcePolicy` a live fetch of that URL would use. Common Crawl
  must never be a way to retrieve a URL that source policy would otherwise
  deny -- it is an alternate way to fetch an *already-approved* URL, not a
  bypass.
- Dispatch requires `CommonCrawlSettings.enabled` and `.policy_approved`.
  No credential is needed (both `index.commoncrawl.org` and
  `data.commoncrawl.org` are public), but the same disabled-by-default,
  explicit-approval posture as every other live-capable adapter still
  applies.
- `warc.py` truncates the embedded HTTP block to the WARC record's own
  `Content-Length` before splitting it into headers/body -- without this,
  the trailing mandatory WARC record terminator (CRLF CRLF) leaks into the
  body. This was verified against a real downloaded record; do not remove
  the truncation without re-verifying against a real WARC record.
- This module is not yet wired into `evidence.services.CollectionService` or
  any `MethodExecutor` -- it produces correct, reusable pipeline output, but
  orchestration (retry/circuit-breaker policy, persistence dispatch) is
  later work, matching A12/A13's "calculator built, not yet wired" pattern.
- Automated tests use injected fake transports and small hand-written WARC
  fixtures (built the same way real ones are structured, verified against
  one real downloaded record) -- never a live network call.
