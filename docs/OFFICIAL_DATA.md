# Official US Data Adapters

Status: A05 complete; all five deliberately small live smoke checks passed on 2026-09-10.

## Purpose and boundary

`mask_api.modules.official_data` retrieves a small, predeclared slice of public
US government data needed by the M1, M3, M4, M5, and M6 research methods. It is
not a crawler and does not discover arbitrary endpoints. Pure request builders,
response parsers, source-neutral records, network transport, and orchestration
gates are separate modules so a later method executor can compose only the
sources required for a named evidence gap.

The current adapters cover:

| Source | Fixed endpoint | Intended evidence | Credential |
| --- | --- | --- | --- |
| Census CBP | `api.census.gov/data/{year}/cbp` | Establishments, employment, annual payroll | Census API key required |
| BLS | `api.bls.gov/publicAPI/v2/timeseries/data/` | Published labor time-series observations | Registration key optional; unregistered requests use smaller limits |
| BEA Regional | `apps.bea.gov/api/data/` | Regional income, employment, and GDP observations | BEA API key required |
| SEC EDGAR submissions | `data.sec.gov/submissions/CIK##########.json` | Filing metadata for named companies | No key; contact email required in User-Agent |
| SAM.gov opportunities | `api.sam.gov/opportunities/v2/search` | Bounded procurement-demand records | SAM public API key required |

Endpoint and parameter choices follow the official
[Census CBP API](https://www.census.gov/data/developers/data-sets/cbp-zbp/cbp-api.2021.html),
[BLS API](https://www.bls.gov/developers/api_signature_v2.htm),
[BEA API guide](https://apps.bea.gov/api/_pdf/bea_web_service_api_user_guide.pdf),
[SEC EDGAR API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces),
and [SAM.gov opportunities API](https://open.gsa.gov/api/get-opportunities-public-api/).
The Census NAICS field is an explicit request input and defaults to
`NAICS2017`; it is never guessed from the data year.

## Safety and cost controls

Every source remains disabled in the source profile. Dispatch requires an
`OfficialApiSettings` instance with both `enabled` and `policy_approved` set,
the matching `official_api` source profile, any required credential, and enough
remaining run budget for one maximum-size response. The transport uses verified
TLS, the exact allowlisted origin/path, no ambient proxies, no cookies, no
redirects, identity content encoding, a bounded timeout, and a bounded response.

Actual external attempts count against the request budget, including HTTP
failures. Successful response bytes count against the byte budget before content
type validation or parsing. HTTP status, retryability, and bounded numeric
`Retry-After` metadata are returned as safe error codes without response or
credential text.

Requests keep public parameters separate from `SecretStr` credential fields.
Stored request provenance contains the endpoint, public query/body, and names of
credential fields, never their values. Parsed batches preserve the exact raw
response bytes and SHA-256 alongside parser version, observations/records, and
explicit unknown/invalid-row issues. Parsers do not access the network, database,
models, or scoring code.

## Source-specific bounds

- Census CBP requests require one year, one two-to-six-digit NAICS code, one
  three-digit employment-size code, one supported geography selector, and an
  explicit NAICS vintage.
- BLS requests reject lowercase/unsafe series identifiers. Without a registration
  key they allow at most 25 series and 10 inclusive years; registered requests
  allow at most 50 series and 20 inclusive years.
- BEA Regional requests allow only bounded table, line, geography, and year
  values and always request JSON. The live smoke uses active table `CAINC4` for
  one county; discontinued `CAEMP25N` is no longer used.
- SEC requests accept one numeric CIK and format it as exactly ten digits. A
  contact email in the User-Agent is mandatory before network dispatch.
- SAM.gov requests require real `MM/DD/YYYY` dates, an ordered range no longer
  than one year, one NAICS code, a page size of 1-1000, and a nonnegative page
  index. Parsers retain procurement/award fields needed for market analysis but
  intentionally exclude point-of-contact details and echoed response links.

## Test and live-smoke contract

Offline fixtures are the normal automated test path and exercise all five
parsers, malformed inputs, request limits, origin enforcement, gates, budget
preflight, provenance redaction, HTTP failures, and content-type rejection.

Live tests are deliberately tiny and are skipped unless both
`MASK_RUN_LIVE_OFFICIAL_SMOKE=1` and `MASK_OFFICIAL_POLICY_APPROVED=1` are set.
They also require `MASK_OFFICIAL_CONTACT_EMAIL` and the source-specific key for
Census, BEA, or SAM.gov. BLS runs under its smaller keyless limits when no
registration key is configured. SEC is keyless but still requires contact identity.
These variables are local-only and must never be committed.

```powershell
uv run pytest apps/api/tests/official_data/test_live_official_smoke.py -q
```

The authorized harness passed Census CBP, keyless BLS, BEA Regional, SEC EDGAR,
and SAM.gov against their current endpoints on 2026-09-10. No credential value,
response body, or credential-bearing URL was logged or committed. The adapters
are not yet registered with the API or worker; persistence and durable job
wiring remain Phase 3 work.
