# Search-intent module rules

Read the root `AGENTS.md`, `progress.txt`, `docs/MODULARITY.md`,
`docs/COST_CONTROL.md`, `docs/SOURCE_AVAILABILITY.md`, and
`docs/SEARCH_INTENT.md` before changing this module.

- Keep contracts, taxonomy, provider parsing, caching, and M6 scoring separate.
- Taxonomy code may classify explicit intent but must not assign or invent M6
  weights. Deterministic scoring belongs to the scoring module under A12.
- Preserve Google Ads integer micros, decimal currency amounts, competition
  values, monthly observations, canonical terms, close variants, provider hash,
  parser version, and taxonomy version. Never substitute bid ranges for CPC.
- Credential and customer IDs belong only in an injected transport. Cache keys,
  artifacts, errors, tests, and provenance must not contain them; use a one-way
  account-scope hash to prevent cross-account cache reuse.
- Keep the provider disabled and fail closed unless its tracked operational
  status, local enable flag, current policy approval, and run budget all allow it.
- Cache before repeated provider calls, use an explicit bounded TTL, and preserve
  immutable records. Keep local artifact paths short enough for native Windows.
- Provider parsers are pure and fixture-backed. Automated tests do not call the
  live Google Ads service, and fixtures are never treated as market evidence.
- Do not register HTTP routes or worker handlers until tenant authorization,
  persistence, and the corresponding phase acceptance are complete.
