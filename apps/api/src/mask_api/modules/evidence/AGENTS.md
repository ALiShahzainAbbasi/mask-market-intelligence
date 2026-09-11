# Evidence module rules

Read the root `AGENTS.md`, `progress.txt`, `docs/MODULARITY.md`,
`docs/SCRAPING_POLICY.md`, `docs/COST_CONTROL.md`, and `docs/COLLECTORS.md`
before changing this module.

- Keep `domain.py`, `contracts.py`, `ports.py`, `policy.py`, `normalization.py`,
  and `services.py` independent of FastAPI, SQLAlchemy, settings, worker runtime,
  and concrete network/database adapters.
- A source-specific collector discovers candidates and parses already-fetched
  bytes. It must not open sockets, write evidence, invoke AI, or calculate scores.
- `http_fetcher.py` is the only network adapter *inside this module*.
  Preserve exact-origin policy checks, public-address resolution, TLS
  verification, disabled ambient proxies/cookies/redirects, response-size
  limits, MIME allowlists, bounded timeouts, and safe errors. Never add
  credential, CAPTCHA, paywall, robots, or access-control bypass behavior.
  `mask_api.modules.common_crawl_data` (A17.5) is a separate module with its
  own network transport that produces a `FetchedResource` a different way
  (a historical archive replay, not a live fetch) and reuses this module's
  `StaticHtmlCollector.parse()`/`normalize_document()` unchanged -- see its
  own `AGENTS.md`. Do not add Common-Crawl-specific logic here.
- The application service owns the ordered
  `discover -> fetch -> parse -> normalize -> persist` use case. Concrete source
  policy and evidence persistence must arrive through typed ports. An explicit
  CLI `LocalArtifactStore` may implement those ports, but must never silently
  replace PostgreSQL in API/worker production wiring.
- Preserve fetched raw bytes separately from parsed/normalized text. Exact
  duplicates keep every occurrence and point to one canonical occurrence; they
  must not inflate analysis counts.
- Limits are source-policy data. Collection stays sequential, bounded, cancellable,
  and free of paid-model calls. A limit produces an honest partial/failed result.
- Every collector needs offline fixtures for success, empty, malformed, changed
  layout/schema, privacy exclusions, and duplicates where applicable. Automated
  tests must not hit uncontrolled live sources.
- Do not register collection HTTP routes or worker handlers until the PostgreSQL
  policy/persistence adapters, tenant authorization, migrations, and live
  acceptance required by Phase 3 exist.
