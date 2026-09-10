# YouTube Data API Adapter

Status: A17.5 offline implementation; no live call has been made yet.

## Purpose and boundary

`mask_api.modules.youtube_data` retrieves a small, predeclared slice of public
YouTube data needed by the M2, M3, and M5 research methods: video search
results (`search.list`) and top-level comment threads on a named video
(`commentThreads.list`). It is a separate module from `official_data`, which
is scoped specifically to US government statutory sources
(`docs/OFFICIAL_DATA.md`); YouTube is a commercial platform reached through an
official, keyed developer API, not a government data source, so it keeps its
own contracts, quota accounting, request builders, parsers, and transport
rather than extending `official_data`'s fixed five-source dispatch tables.

It is not a crawler, does not use OAuth, and never touches private,
unlisted, or channel-owner-only data -- only what a signed-out viewer can see
through the public API. It does not scrape the YouTube web UI.

| Endpoint | Fixed path | Intended evidence | Quota cost |
| --- | --- | --- | --- |
| `search.list` | `www.googleapis.com/youtube/v3/search` | Discover videos discussing a market's pain, workflow, or competitors | 100 units |
| `commentThreads.list` | `www.googleapis.com/youtube/v3/commentThreads` | Public audience discussion (pain, workarounds, dissatisfaction) on one video | 1 unit |

Endpoint and parameter choices follow the official
[YouTube Data API v3 reference](https://developers.google.com/youtube/v3/docs)
and its [quota cost table](https://developers.google.com/youtube/v3/determine_quota_cost).

## Safety and cost controls

The source stays disabled in the source profile by default. Dispatch requires
a `YouTubeApiSettings` instance with both `enabled` and `policy_approved` set,
the matching `official_api` source profile with `operational_status:
available`, and the credential named `MASK_youtube_API_KEY` in the local
environment (the owner-supplied name, reused as-is). The transport uses
verified TLS, the exact allowlisted host/path, no ambient proxies, no
cookies, no redirects, identity content encoding, a bounded timeout, and a
bounded response.

YouTube meters cost in quota units per endpoint (a free tier of 10,000 units
per day by default), not request count or bytes, so the shared run
`BudgetLedger` cannot express it. `YouTubeQuotaLedger` reserves the exact
per-endpoint unit cost before every call, in addition to (not instead of) the
shared request/byte budget. A provider-reported `quotaExceeded` response
(HTTP 403 with that specific error reason) raises the distinct
`YouTubeQuotaExceededTransportError` rather than a generic HTTP failure, so a
caller can record `SOURCE_UNAVAILABLE_QUOTA` and continue the run with other
providers instead of failing it outright.

Requests keep the public query separate from the `SecretStr` API key. Stored
request provenance contains the endpoint and public query, and the name of
the credential field, never its value. Parsed batches preserve the exact raw
response bytes and SHA-256 alongside parser version, videos/comments, and
explicit unknown/invalid-item issues. Parsers do not access the network,
database, models, or scoring code.

## Evidence boundary

Search and comment results returned by this module are raw evidence, not
accepted evidence. They must still pass through the same relevance
classification and grounding validation (`docs/GROUNDING_VALIDATION.md`) as
any other source before they can influence a method score. This module
performs no classification, persona assignment, or scoring.

## Source-specific bounds

- Search requests require a 1-200 character query, 1-50 results, a two-letter
  region code, an optional RFC 3339 UTC `publishedAfter` timestamp, and an
  optional page token.
- Comment-thread requests require a syntactically valid video ID, 1-100
  results, and an optional page token. Comments with empty text are recorded
  as a parse issue and dropped rather than kept as empty evidence.

## Test contract

Offline fixtures are the normal automated test path and exercise both
parsers (including a missing-title video and an empty-text comment), request
validation limits, origin enforcement, quota accounting (including a
cheaper `commentThreads` call still fitting after `search` exhausts most of a
small budget), the distinct quota-exceeded error path, generic HTTP failures,
and content-type rejection. No live YouTube call has been made; a live smoke
test analogous to `docs/OFFICIAL_DATA.md`'s is a follow-up under A17.5, not
yet implemented.
