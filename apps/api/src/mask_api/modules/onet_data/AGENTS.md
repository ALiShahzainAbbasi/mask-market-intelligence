# O*NET data module rules

Read the root `AGENTS.md`, `progress.txt`, `docs/OFFICIAL_DATA.md`, and
`docs/MODULARITY.md` before changing this module.

- This module uses the official O*NET **downloadable database** release
  (a static ZIP of CSV tables), never the separate O*NET Web Services API,
  which needs its own approval this project does not have. Do not add a
  Web Services credential or endpoint here.
- Keep contracts, the network transport (HEAD/download only, no ranged
  fetch -- the whole release is one bounded ~16MB archive, unlike Common
  Crawl), the local cache, CSV parsers, and bootstrap orchestration in
  separate files, matching `official_data`/`youtube_data`'s split.
- The local cache (`cache.py`) is deliberately not
  `research_runner.ports.ArtifactStore`: that store's per-run root and
  raw/normalized/evidence layout are shaped for one research run's output,
  while the O*NET archive is one static dataset shared across every run.
  Do not stretch the per-run store to fit this cross-run concern.
- O*NET publishes no independent checksum for a release. `sha256` on
  `OnetDatasetDescriptor` is self-computed over the downloaded bytes for
  local integrity verification only (catching on-disk corruption on a
  later read), not verification against a publisher-supplied value --
  never describe it as the latter in docs or logs.
- `OnetBootstrapper.ensure_dataset()` must always issue a cheap HEAD
  request before deciding whether to redownload, and must skip the ~16MB
  GET when the cached descriptor's `content_length`/`etag` already match
  the HEAD response. Never redownload unconditionally "to be safe."
- CSV column names and blank-value behavior (`Task Type` and `Incumbents
  Responding` are sometimes empty in the real data) were verified against
  a real O*NET 31.0 release, not guessed. If a future dataset version
  changes column names, update the parser deliberately and re-verify
  against the real file -- do not silently swallow a header mismatch.
- Dispatch requires `OnetBootstrapSettings.enabled` and `.policy_approved`.
  Parsers never open sockets, read credentials, or write storage.
- Imported occupations/tasks are raw reference data, not accepted
  evidence by themselves. Cross-referencing them with BLS series and
  turning them into M3 method input is later work, not this module's job.
- Automated tests use injected fake transports, a `tmp_path` cache, and
  small hand-written fixture CSVs matching the verified real column
  headers -- never the full ~16MB real download and never a live network
  call.
