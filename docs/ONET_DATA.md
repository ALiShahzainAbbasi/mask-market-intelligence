# O*NET Database Bootstrap

Status: A17.5 complete. Offline suite passes; live download succeeded end
to end on the third attempt (see "Live smoke status" below).

## Purpose and boundary

`mask_api.modules.onet_data` uses the official **O*NET downloadable
database** (a static, versioned ZIP release of CSV tables), never the
separate O*NET Web Services API, which needs its own approval this project
does not have and is out of scope. It downloads one bounded ~16MB archive,
verifies what was received, caches it locally so later runs do not
redownload it, and imports two tables for M3 occupation/task/workflow
mapping:

| Table | Columns imported | Intended evidence |
| --- | --- | --- |
| `occupation_data.csv` | O*NET-SOC Code, Title, Description | Occupation identity, for cross-referencing with BLS series |
| `task_statements.csv` | O*NET-SOC Code, Task ID, Task, Task Type, Incumbents Responding, Date, Domain Source | Task-level workflow evidence |

Column names and blank-value behavior (`Task Type` and `Incumbents
Responding` are sometimes empty in the real release) were verified against
a real O*NET 31.0 database download, not guessed. The much larger
`task_ratings.csv` (39MB, importance/frequency ratings per task) and
`work_activities.csv` (12MB) are intentionally not imported in this first
pass -- a documented, deferred follow-up, not a silent gap.

## Bootstrap pipeline

`OnetBootstrapper.ensure_dataset()`:

1. Requires `OnetBootstrapSettings.enabled` and `.policy_approved`.
2. Reads any cached `OnetDatasetDescriptor` (version, content length,
   ETag, self-computed SHA-256).
3. Issues one HEAD request (charged against the shared `BudgetLedger`) to
   read the remote's current Content-Length and ETag.
4. If a cached descriptor already matches, returns it without
   redownloading. Otherwise downloads the full archive (also
   budget-gated), verifies the response's content type, computes its own
   SHA-256 over the received bytes, and writes both the archive and its
   descriptor atomically to a small dedicated local cache
   (`mask_api.modules.onet_data.cache.LocalOnetCache`, not the per-run
   `ArtifactStore` -- this dataset is shared across every run, not scoped
   to one).

O*NET does not publish an independent checksum for a database release, so
the descriptor's `sha256` is a **local integrity check** (catching on-disk
corruption on a later read), not verification against a publisher-supplied
value -- `import_batch()` recomputes and compares it before trusting a
cached archive.

`OnetBootstrapper.import_batch()` reads the cached archive, extracts only
the two needed CSV members from the ZIP (not every file in the release),
and parses them into typed, validated `OnetOccupation`/`OnetTaskStatement`
records. A row missing its SOC code, title, description, task ID, or task
text is dropped as a recorded parse issue rather than kept with an invented
value.

## Evidence boundary

Imported occupations and tasks are raw reference data, not accepted M3
evidence by themselves. Cross-referencing them with BLS series and turning
them into method input for the M3 calculator (`docs/WORKFLOW_INTELLIGENCE.md`)
is later work, not this module's job.

## Test contract

Offline tests use small hand-written fixture CSVs matching the verified
real column headers (never the full ~16MB release) and a fake transport --
covering both parsers (including the real data's blank-value cases and
malformed-header rejection), the local cache (round-trip, corruption
detection, path-traversal rejection), and the bootstrapper (download once,
skip-download-when-cache-matches, redownload-when-remote-changed,
disabled/policy-not-approved short-circuits, and end-to-end archive
extraction plus a cached-archive-checksum-mismatch detection).

A gated live smoke test (`test_live_onet_dataset_bootstrap_and_import`,
gated by `MASK_RUN_LIVE_ONET_SMOKE=1` and `MASK_ONET_POLICY_APPROVED=1`,
matching `docs/OFFICIAL_DATA.md`'s pattern) downloads the real O*NET 31.0
release once against `www.onetcenter.org`, imports it, and asserts a
sane minimum row count for both tables. Unlike the other official sources'
"deliberately small" live checks, this one necessarily transfers the full
archive once, since O*NET publishes no smaller sample -- it is still a
single, keyless, zero-cost, one-time call, and the cache means it will not
repeat on a later run against an unchanged release.

### Live smoke status

Run three times against the real server, honestly reported:

1. **First attempt** (~17 minutes) completed the download, but
   `import_batch()` then failed with `zipfile.BadZipFile`. Inspection
   showed the cached archive was 14.68MB against a declared 16.24MB --
   the transport's single `.read(n)` call had silently returned fewer
   bytes than the server promised, and nothing checked for that before
   writing to cache. This was a real bug, not an environment quirk by
   itself: **fixed** by (a) making `UrllibOnetTransport.download()` loop-
   read in bounded chunks to true EOF instead of trusting one `.read(n)`
   call, and (b) making `_download_and_cache()` explicitly compare the
   received byte count against the HEAD response's `Content-Length` and
   raise a retryable `onet.download_incomplete` error rather than ever
   caching a short read. Both are covered by new offline tests.
2. **Second attempt** (~17 minutes, after the fix) did not silently
   truncate again; instead the connection genuinely dropped mid-transfer,
   which the loop-read now correctly surfaced as a caught, clean,
   retryable `onet.network_error` -- proving the fix works under the
   exact real adverse condition that caused the original bug, rather than
   crashing uncaught or corrupting the cache.
3. **Third attempt** (~10.5 minutes) **passed completely**: downloaded
   the full 16,237,378-byte archive (byte-identical -- same SHA-256,
   `55033fc6...` -- to an independently downloaded reference copy used to
   verify the parser during implementation), imported it, and confirmed
   1,016 occupations and 18,838 task statements. A follow-up query for
   O*NET-SOC code `49-9021.00` ("Heating, Air Conditioning, and
   Refrigeration Mechanics and Installers") returned 30 real Core/
   Supplemental task statements (e.g. "Discuss heating or cooling system
   malfunctions with users to isolate problems...", "Test electrical
   circuits or components for continuity...") -- genuine M3 workflow
   evidence for the `us_hvac_10_99` sample market.

Net effect: the connection to `onetcenter.org` from this environment is
unreliable (roughly 16KB/s and prone to mid-transfer drops), so a live
run should be expected to need one or two retries, but the bootstrap
pipeline itself -- download, integrity verification, caching, and
import -- is now confirmed correct end to end against the real service,
not just offline fixtures.
