# Source Discovery

Status: A04 implemented; live provider execution disabled by default.

## Deterministic query plans

`mask_api.modules.discovery.query_planner` derives bounded, stable queries only
from the validated market's seed terms, problems, buyer titles, geography, and
the selected method IDs. Each query records its method, intent, source terms,
version, and SHA-256 identifier. M8 and M10 intentionally have no public-search
templates because only qualified real primary research or funnel telemetry can
satisfy them.

Plans are canonical regardless of input method order, deduplicate exact
case-insensitive query text, stop at a configured query count, and enforce the
provider's 600-character/75-word maximum. Search results are discovery leads,
not accepted evidence: each downstream URL still needs its own current source
policy and collection approval.

## Optional Brave Search adapter

The adapter uses the official Web Search endpoint
`https://api.search.brave.com/res/v1/web/search`, the required
`X-Subscription-Token` request header, and a pinned `Api-Version: 2023-01-01`
header. It asks for strict safe search, accepts at most 20 results per page and
10 pages, follows `more_results_available`, and uses no redirect, cookie, or
ambient proxy behavior. See Brave's official
[Web Search API](https://api-dashboard.search.brave.com/api-reference/web/search/get),
[authentication guide](https://api-dashboard.search.brave.com/documentation/guides/authentication),
and [versioning guide](https://api-dashboard.search.brave.com/documentation/guides/versioning).

No live request is possible unless all of these are present:

1. the `brave_search` commercial source profile;
2. explicit adapter enablement;
3. explicit policy approval;
4. an injected secret API key;
5. a positive per-request cost estimate; and
6. a positive run-level paid-cost budget with enough request/byte capacity.

The adapter reserves worst-case request capacity before network I/O, records
actual requests/response bytes/cost afterward, preserves each raw JSON page and
its hash, retains endpoint/query/page/time/rank provenance, stops pagination when
the provider says no more results exist, and deduplicates URLs without collapsing
case-sensitive paths. HTTP/rate/network/schema errors are classified without
persisting response bodies or credentials in exception messages. A caller may
honor the returned bounded `Retry-After`; this adapter performs no hidden retries.

Tests are fixture-only. No Brave account, key, subscription, or paid request was
created by A04.
