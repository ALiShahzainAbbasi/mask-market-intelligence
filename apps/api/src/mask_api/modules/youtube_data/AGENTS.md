# YouTube Data module rules

Read the root `AGENTS.md`, `progress.txt`, `docs/OFFICIAL_DATA.md`,
`docs/SCRAPING_POLICY.md`, and `docs/MODULARITY.md` before changing this module.

- This is a fixed-scope adapter for two YouTube Data API v3 endpoints
  (`search.list`, `commentThreads.list`) using an API key only. No OAuth, no
  private/unlisted data, no channel-owner-only endpoints, and no scraping of
  the YouTube web UI. It consumes only public data a signed-out viewer can see.
- Keep contracts, quota accounting, request builders, parsers, and network
  transport in separate files, matching `official_data`'s split. Parsers never
  open sockets, read credentials, or write storage.
- YouTube meters cost in quota units per endpoint, not request count; the
  shared `BudgetLedger` cannot express this, so `YouTubeQuotaLedger` reserves
  quota units before every call in addition to the shared request/byte budget.
- Dispatch requires `YouTubeApiSettings.enabled` and `.policy_approved`, a
  matching `official_api` source profile with `operational_status: available`,
  and `MASK_youtube_API_KEY` (or whatever name the source-policy owner has
  actually configured -- never invent or duplicate a differently named key).
- A provider-reported `quotaExceeded` (HTTP 403 with that error reason) must
  raise the distinct `YouTubeQuotaExceededTransportError`, not a generic HTTP
  failure, so a caller can record `SOURCE_UNAVAILABLE_QUOTA` and continue the
  run with other providers instead of failing it.
- Search and comment results are raw evidence, not accepted evidence. They
  must still pass through the same relevance/grounding pipeline as any other
  source before they can influence a method score; this module performs no
  classification, scoring, or persona assignment.
- Automated tests use injected fake transports and labelled fixtures; they
  never call a live endpoint or treat fixture data as market evidence.
