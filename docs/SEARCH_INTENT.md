# Search Intent and Google Ads Boundary

Status: A07 offline foundation implemented; Google Ads live access remains on hold.

`mask_api.modules.search_intent` owns credential-free historical-metrics
contracts, deterministic keyword-intent classification, pure Google Ads response
normalization, and the keyword-metrics cache port/local adapter. It does not own
M6 formula calculation, scoring, persistence composition, credentials, or HTTP
routes.

The versioned `keyword-intent-v1` taxonomy classifies only explicit lexical
signals into problem, informational, solution, commercial, comparison,
transactional, or competitor-switching intent. Unclear phrases remain `UNKNOWN`.
No intent weight is invented here; A12 will apply only the approved formula
inputs and must keep missing required values unknown.

Google Ads response normalization preserves canonical keyword text, close
variants, twelve-month observations, average monthly searches, competition
level/index, optional average CPC, and low/high top-of-page bid ranges. Monetary
values retain both exact integer micros and decimal amounts with the configured
account currency. Downstream code must not call a bid “CPC” or call a non-USD
amount “USD.”

The cache key includes normalized keywords, account-scope hash, geography,
language, network, date range, currency, and CPC-inclusion policy—never a
customer ID or credential. Local cache records are immutable, expire after a
configurable period no longer than 31 days, and use shortened collision-resistant
paths for Windows compatibility while validating the full hash inside each record.

The checked-in Google Ads source remains `approval_pending`, disabled by default,
and policy-gated. No credential-bearing transport is bundled or composed. The
adapter therefore stops before cache or transport access under the current lean
profile. Fixture parsing and fake injected transports are tests, not market
evidence or proof of live access.
