# Source Utilization Register — MASK AI Market Intelligence

**Date:** 2026-09-17, finalized and corrected 2026-09-18 (see the Capterra entry below and `CURRENT_SYSTEM_AUDIT.md` §9 for what changed). Chain tracked per source: **availability → permission → collection → valid records → extracted findings → methodology input → score → report.** All entries **[VERIFIED]** against `configs/sources/default_us_public.yaml`, the relevant adapter module, and real `outputs/runs/` artifacts unless marked otherwise. Secret values were never read — only key *names* were confirmed present in `.env.official.local`.

## Headline finding

Across every real, persisted method-result JSON artifact in `outputs/runs/` (a repository-wide scan for a non-`UNKNOWN` status across every `*result*.json` file returns exactly one hit: `m9_us_hvac_10_99_20260914T191202Z/m9_result.json`, `status: complete, score: 6.476`), only **M9 for `us_hvac_10_99`** has a directly-verifiable, machine-readable complete score. **M1 for `us_hvac_10_99` is also real and complete (6.34/10)**, well-evidenced by 9 individually-inspectable raw Census query responses and a matching narrative/methodology document — but, unlike M9, its computed result was never persisted as a JSON artifact (`scripts/run_census_m1.py` prints it but does not write it to disk), so it is reconstructed from raw data plus documentation rather than independently verifiable from one scored object. Combining both: **exactly two method/market pairs — M1 and M9, both `us_hvac_10_99` only — have ever reached a complete, non-`UNKNOWN` score**, though on two different tiers of artifact-level verifiability. This single fact governs almost every "score" and "report" column below: most sources were genuinely collected but never converted into a scored method, because *other*, still-missing components of that method's formula — not the source itself — kept the method `UNKNOWN`.

---

## Register

### Census CBP
- **Availability:** registered, `operational_status: available`, credential present (`MASK_CENSUS_API_KEY`).
- **Permission:** `policy_status: allowed`.
- **Collection:** real, repeated — 9+ real queries per market run (`outputs/runs/m1_census_*/raw/official_data/census_cbp/*.json`, `outputs/runs/ingest_us_hvac_10_99_*/raw/census_cbp.json`), plus 56-state and 51-metro discovery-stage pulls.
- **Valid records:** 23,617 real target-band establishments for HVAC alone; full national coverage for all 40 Wave A candidates.
- **Extracted findings:** yes — typed `SourceRecord`s via `official_data/parsers.py`.
- **Methodology input:** the *only* input to canonical M1 (`method_metrics/m1.py`); also feeds an informal `m1_light`/`regional_prescreen_score` used only in screening scripts, never the canonical calculator.
- **Score:** M1 = 6.34/10 COMPLETE (HVAC only).
- **Report:** cited by name/figure in `M1_Source_and_Methodology_us_hvac_10_99.docx`, `us_hvac_10_99_StageA_*.docx`.
- **Gap:** the persisted M1 result itself is not saved as a standalone JSON artifact anywhere under `outputs/runs/` — the 6.34 figure is recoverable only from `progress.txt` and the generated `.docx`, not a machine-readable contract object. Minor reproducibility gap.

### BLS (keyless)
- **Availability:** registered, no credential required.
- **Permission:** allowed.
- **Collection:** real — 36 monthly observations, series CES2023800001 (`outputs/runs/ingest_us_hvac_10_99_*/raw/bls.json`).
- **Extracted findings:** raw only — no parser converts it into any pain/spend/wage field consumed downstream.
- **Methodology input:** **none.** Explicitly excluded from M1 by design (`us_hvac_10_99_StageA_Technical_Evidence_Report.docx`: *"Mixing in BLS... here would silently change the approved M1 methodology"*).
- **Score:** never contributes.
- **Report:** narrative context only.
- **Unused opportunity:** BLS wage series could plausibly inform M4's `annual_burden`/labor-cost estimation if a mapping were built — currently untouched.

### BEA Regional
- **Availability:** registered, `available`, credential present (`MASK_BEA_API_KEY`).
- **Permission:** conditional.
- **Collection:** real, but only at the discovery/region-screening stage — explicitly `SKIPPED` for the per-market HVAC M1 run itself (`ingest_us_hvac_10_99_*/raw/_summary.json`: *"us_hvac_10_99 defines no target region"*). Real CAINC4 data exists for 28 states (`discover_regions_us_hvac_10_99_*/state_regional_discovery.json`).
- **Valid records:** real per-capita/personal-income figures for 28 states.
- **Extracted findings:** yes, parsed into `bea_enrichment` records.
- **Methodology input:** feeds only the informal `regional_prescreen_score`, never M1 or M4's actual calculators.
- **Score:** never contributes to any canonical M1–M9 score.
- **Report:** region-screening narrative context only.
- **Registry/execution mismatch:** `operational_status: available` for methods `[M1, M4]` is technically true (credentialed, callable) but misleading in effect — neither M1 nor M4's real breakdown for HVAC cites a BEA value.

### SEC EDGAR
- **Availability:** registered, keyless.
- **Permission:** allowed.
- **Collection:** real — 1,000 filings, Comfort Systems USA Inc (CIK 1035983) (`ingest_us_hvac_10_99_*/raw/sec_edgar.json`).
- **Extracted findings:** raw filing metadata only (form type, date, accession number) — no text-content parsing for pricing/competitive claims exists anywhere.
- **Methodology input:** none found in any M4/M5 breakdown.
- **Score:** never contributes.
- **Report:** descriptive company context only.

### SAM.gov
- **Availability:** registered, credentialed (`MASK_SAM_API_KEY`).
- **Permission:** conditional.
- **Collection:** real — 25 opportunities/awards, NAICS 238220.
- **Extracted findings:** raw only.
- **Methodology input:** none — declared as a `pain_and_workflows`/`competitors_and_pricing`/`search_demand` fallback in the registry, but no M4/M5/M6 result anywhere cites a SAM.gov record, and structurally it has no CPC/volume/pricing fields M6 needs.
- **Score:** never contributes.
- **Report:** narrative context only.

### USAspending
- **Availability:** registered, keyless.
- **Permission:** allowed.
- **Collection:** real — 25 awards, 2015–2026, $642,710,097 total.
- **Extracted findings:** raw only.
- **Methodology input:** none — same fallback-declared-but-unused pattern as SAM.gov.
- **Score:** never contributes.
- **Report:** narrative context only.
- **Unused opportunity:** the real dollar `award_amount` field is exactly the shape of value M4's `annual_existing_paid_spend_usd` needs conceptually (a real, dated dollar figure tied to a named entity) — never mapped, because federal contract spend is not target-market software spend; would need a genuinely different, non-federal source class to matter for M4.

### YouTube Data API v3
- **Availability:** registered, credentialed (key present under the literal name `MASK_youtube_API_KEY` — note the lowercase-service-name casing, a real, harmless but inconsistent naming convention vs. the more common `MASK_<SERVICE>_API_KEY` uppercase pattern used elsewhere).
- **Permission:** conditional.
- **Collection:** real and by far the most productive source in the project. HVAC alone: 1,409 + 192 real comments across two separate collection passes (pain + competitor evidence). Reused across all 14 Phase 3 markets at a capped depth (200 candidates/market) and Wave B at an even thinner depth (15 candidates/market).
- **Documentation staleness note:** `docs/YOUTUBE_DATA.md`'s own status line ("no live call has been made yet") is **contradicted by real run evidence** — this doc has not been updated to reflect the extensive live use that has since occurred.
- **Extracted findings:** yes — Gemini-extracted, grounding-validated pain mentions and competitor mentions.
- **Methodology input:** feeds M2 (pain), M4's `commercial_intent` component, M5's `competitor_proof`/`unresolved_gap` components, and M9's evidence base.
- **Score:** partial, real contributions to M4 and M5 for HVAC (neither reached COMPLETE); full contribution to M9's real 6.476 score.
- **Report:** cited extensively, by name and count, in every generated report.

### O\*NET downloadable database
- **Availability:** registered, keyless, static dataset.
- **Permission:** allowed.
- **Collection:** real, live-verified after two earlier failed attempts (a genuine silent-truncation bug, fixed) — 1,016 occupations, 18,838 task statements, SHA-256-verified 16.2MB download.
- **Extracted findings:** yes — task statements become `WorkflowStepEvidence.step_name` scaffolding for M3, at 100% grounding success in every market attempted.
- **Methodology input:** partial and structural — supplies the *taxonomy* of what work exists, never the *metrics* (frequency/duration/failure-rate/consequence) M3's formula requires. This is the single best-evidenced Source mismatch in the whole project: 13/13 real M3 attempts (HVAC + 12 Phase 3 markets) resolved UNKNOWN with identical, predictable root cause.
- **Score:** M3 has never reached COMPLETE for any market, ever.
- **Report:** cited (task counts, SOC code, sample tasks) in every generated Technical Evidence report as context; never as a scoring contributor.

### Common Crawl (targeted CDX + ranged WARC)
- **Availability:** registered as a real, working module (`common_crawl_data`) — **but not listed as a `sources:` entry in `configs/sources/default_us_public.yaml` at all**, a real gap between what was built/used and what the canonical registry tracks.
- **Permission:** ad hoc, in-process `SourcePolicy` objects constructed per script run (Jobber, Workyard, Workiz, Procore pricing pages) — not a persisted, reusable policy.
- **Collection:** real, mixed outcome, all collected **2026-09-17, this session, after every currently-existing report was already generated**:
  - Jobber pricing: **fetched**, 200, real $29–$699/mo tier text (two different figures appear across two separate real captures — see "duplicated evidence" note below).
  - Workyard pricing: **fetched**, 200, real "$6/user/month starting" text.
  - Workiz pricing: **fetched** (on a retry against a different collection after the first attempt found no capture).
  - Procore pricing: **failed** — real, repeated transient CDX 502/504 errors across all 3 collections tried, and once a capture *was* found, its real archived record exceeded even a 25MB retrieval budget. Procore's live pricing page independently confirmed (via direct browser fetch) to publish no numeric tiers at all (quote-only), so this gap costs little real information.
- **Extracted findings:** no parser converts the fetched HTML into a structured price record — it sits as raw HTML/text plus a hand-read `normalized_text_excerpt`.
- **Methodology input:** **zero, currently.** Confirmed by exhaustive grep: no reference to `jobber_pricing`, `competitor_pricing_common_crawl`, or any of these run directories exists anywhere in `apps/`, `configs/`, `docs/`, or any script other than the ones that generate them.
- **Score:** never contributes to any M4/M5 result. Concretely: HVAC's own real `m5_result.json` still shows `pricing_proof: missing` despite this real pricing data existing on disk at the same time.
- **Report:** **zero occurrences** in any generated report — confirmed both by full-text search and by file-modification-time ordering (every real report predates this collection).
- **Mis-targeting risk (see `CURRENT_SYSTEM_AUDIT.md` §4 item 8):** the Jobber script's own docstring claims to unblock M4's `annual_existing_paid_spend_usd` — the wrong field. A vendor's advertised list price is legitimate, correctly-typed evidence for **M5's** `pricing_proof` (methodology explicitly allows "Starting at"-labelled pricing there), never for M4's true-spend field.

### Capterra reviews (new this session) — **[CORRECTED 2026-09-18: this source is not authorized for use; see below]**
- **Availability:** **not registered anywhere** — zero occurrences of "capterra" in `configs/sources/default_us_public.yaml` or any `apps/api/src/mask_api/modules` code. No `SourcePolicy`, no `source_family` enum entry, no collector class exists.
- **Permission — corrected 2026-09-18, this is the most important line in this entry.** The original 2026-09-17 draft of this register described permission as "an ad hoc, manual robots.txt review... performed inline in conversation." That was accurate as far as it went but incomplete, and the conclusion it supported was wrong. `docs/SCRAPING_POLICY.md` requires a **terms-of-service** review as a separate, named, mandatory precondition alongside robots.txt (§2: *"the source policy, terms, robots controls, rate limits, and applicable law permit it"*; §4: a recorded *"terms and robots review dates"*) — this was never done for Capterra. A 2026-09-18 verification pass performed it directly: Capterra's real, live General User Terms (`https://www.capterra.com/legal/terms-of-use/`, Section 10, "PROHIBITED AUTOMATED ACCESS, SCRAPING, AND DATA EXTRACTION," read verbatim from the page DOM) explicitly prohibit, without Capterra's express prior written consent: automated/programmatic/headless-browser extraction of review content, **regardless of robots.txt permissiveness** (the clause names robots.txt directives explicitly as something the restriction survives), and using extracted content to "train, test, validate, fine-tune, evaluate, or improve any machine-learning model, generative AI system... whether for internal or external use." Both of these are exactly what was done: a `get_page_text` browser collection, followed by Gemini-based extraction/evaluation of the collected review text. **Corrected conclusion: this collection was not authorized. Robots.txt permissiveness does not establish authorization when the site's own Terms of Use separately and explicitly prohibit the activity — the two checks are independent and both are required.** See `CURRENT_SYSTEM_AUDIT.md` §9.1 for the full clause text and disposition recommendation.
- **Collection:** real — 4 raw text files (`outputs/runs/capterra_reviews_raw/{jobber,workyard,workiz,procore}_page1.txt`), collected via the Browser tool's raw `get_page_text` (not an AI summary, specifically so `evidence_span` exact-substring grounding would remain possible). This collection method is itself one of the specific methods the real Terms of Use name as prohibited ("headless browsers... whether or not such content is publicly accessible").
- **Valid records:** 32 hardcoded reviewer documents, transcribed by hand into a literal Python list (`scripts/extract_phase3_capterra_pain.py:135`, `DOCUMENTS: list[dict[str, object]]`) — 6 Jobber, 7 Workyard, 7 Workiz, 12 Procore.
- **Extracted findings:** real, partial, and — per the correction above — obtained through a method the source's own terms prohibit. First extraction attempt: 6 mentions from 32 documents, heavily degraded by real HTTP 429 rate-limiting from the concurrently-running M5 background process sharing the same Gemini key (only 6 of 32 documents actually got a Gemini response before the run was judged complete). A **second attempt, made during the original 2026-09-17 audit** (with retry/backoff added specifically to survive the 429s) reached only 3 real mentions from the first 9 documents before **crashing on an unhandled `BudgetLimitExceeded` exception** — the retry loop's real request volume (up to 5 attempts × 20-80s backoff per failed document) pushed total real Gemini requests past the script's own `BudgetLedger(max_requests=42)` ceiling, and `BudgetLimitExceeded` (from `research_runner.budgets`) is not a subclass of the `GeminiError` the script's `except` clause catches — a real, live-observed, unhandled crash. **[VERIFIED]** As of the 2026-09-18 finalization pass, this process is confirmed no longer running (the task exited after the crash) and has **not** been restarted or continued, per instruction — independent of the crash, it should not be restarted at all until the authorization question above is resolved.
- **Methodology input:** none, for either extraction attempt — both postdate every real M2/M4/M5 result on disk, and, per the correction above, **must not be wired into any score** until the owner resolves the authorization question, regardless of the engineering effort required.
- **Score:** none.
- **Report:** zero occurrences in any generated report.
- **Disposition (added 2026-09-18):** the raw files and extraction outputs have not been deleted or modified by this audit, per the explicit instruction to preserve historical evidence — they remain on disk exactly as produced. This audit recommends the owner decide, ideally with legal input, between: (a) seeking Capterra's express written consent for this specific research use (the clause's own stated carve-out), (b) formally accepting the risk of retaining and using data collected in violation of the site's terms, or (c) treating the artifacts as quarantined/unusable and pursuing a genuinely different evidence source for this evidentiary gap. This audit does not make that decision.
- **Is this a real, reusable source, independent of the authorization question?** No. Even setting the compliance issue aside, it is a one-off manual transcription script, not comparable in engineering terms to Census/YouTube/O\*NET: no registered `SourcePolicy`/`source_family` entry, no real `capterra_data` module, a hardcoded 32-item document list instead of a programmatic fetch+parse pipeline, and the unfixed retry/budget interaction bug above. These engineering gaps are moot unless and until the authorization question is separately resolved.

### Gemini (analysis provider — cross-cutting, not a data source per se)
- **Availability:** the only analysis provider with a real, concrete network transport (`UrllibGeminiTransport`); OpenAI's adapter has no concrete transport at all and cannot call a model.
- **Permission:** governed by `ModelExecutionPolicy`/`enabled`+`policy_approved` flags, not a `SourcePolicy`.
- **Collection:** real, extensive, live-verified — hundreds of cached calls under every `outputs/runs/*/artifacts/cache/analysis/` directory.
- **Extracted findings:** this *is* the extraction step (structured claims validated against exact source-text spans before anything becomes scoring input).
- **Methodology input:** indirect but pervasive — the mechanism turning raw text into M2/M5/M9-consumable records.
- **Score:** never calculates a score itself, by explicit design rule (`docs/ANALYSIS_PROVIDER.md`: *"Gemini may only extract/classify/summarize -- it never calculates a score, confidence index, gate, veto, or ranking"*) — verified consistent with everything found in this audit.
- **Report:** call-disposition counts cited in Technical Evidence reports.
- **Operational constraint observed live during this audit:** two research processes (M5 competitor discovery, Capterra extraction) sharing one Gemini key produced real, sustained HTTP 429 contention for over an hour of this audit's duration — a genuine capacity constraint on how much can be run concurrently against the free tier, not a code defect.

### Google Ads Keyword Planner (search_intent / M6)
- **Availability:** registered, `operational_status: approval_pending`.
- **Permission:** conditional; developer-token application submitted by the owner but not yet approved as of this audit.
- **Collection:** never. `GoogleAdsHistoricalMetricsTransport` is a bare `Protocol` with zero concrete implementations anywhere in the repo.
- **Extracted findings:** n/a.
- **Methodology input:** none — every M6 component is `missing` in the one real run that exists (HVAC).
- **Score:** M6 has never reached COMPLETE for any market.
- **Report:** cited as a documented, explicit hold.
- **What it would take:** both the owner's account approval **and** a genuinely new engineering artifact (a concrete transport class) — neither alone unblocks M6.

### Google Trends
- **Availability:** not registered anywhere; no code module exists.
- **Status:** tested live this session (a real, undocumented internal CSV-export endpoint was found) and **deliberately not adopted** — it can supply only 1 of M6's 5 required formula components (`trend`, a relative index), never `weighted_avg_cpc_usd` or absolute `weighted_monthly_volume`, and scaling an undocumented endpoint was judged a real ToS/reliability risk. The real, sanctioned alternative (Google's own `bigquery-public-data.google_trends` public BigQuery dataset) would need the owner's own GCP project/service-account credential — a real, if lower-friction, access dependency.
- **Methodology input / score / report:** none, and this is a considered, documented "no," not an oversight.

### Meta Ad Library
- **Availability:** registered, `operational_status: approval_pending` (implies an official API).
- **Permission:** conditional (per registry).
- **Collection:** real, but via **manual browser navigation** (`facebook.com/ads/library`), not the registered official API — a real mismatch between what's registered and what actually produced the evidence, repeated identically across all 6 real M7 runs.
- **Extracted findings:** yes — advertiser counts and presence, manually read and recorded.
- **Methodology input:** feeds half of M7's `meta_fit` component in every real M7 run.
- **Score:** real, partial `weighted_contribution` to `meta_fit` in every M7 run — M7 itself never reaches COMPLETE regardless (other components missing).
- **Report:** cited by name in every M7-bearing report.

### Static HTML / RSS-Atom (registered fallback collectors)
- **Availability:** registered, `available`, no credential required.
- **Permission:** conditional.
- **Collection:** the `StaticHtmlCollector.parse()` logic is real and reused unchanged by Common Crawl's module — but as a directly-dispatched, automated collector against a registered URL, **no evidence of independent execution was found**. M7's buyer-identification evidence (4-6 company homepages per market) was gathered via **manual** homepage checks, citing "SCRAPING_POLICY.md path #6 (manual evidence capture)," not an automated `static_html` dispatch through `SourcePolicy`.
- **Methodology input:** real, partial contribution to M7's `buyer_identification`/`contact_coverage`/`channel_diversity` in every real M7 run — always manually sourced.
- **Score:** contributes but M7 never reaches COMPLETE.
- **Report:** cited (company names, HTTP 403 exclusions).

### Registered but never executed at all (no code module exists)
**[VERIFIED]** by exhaustive module-directory search — none of these have any implementing code, not even an offline-tested stub:
- **Google Places** (`operational_status: paid_hold`) — no module.
- **Reddit** (`approval_pending`) — no module.
- **Firmographic data providers** (`paid_hold`) — no module.
- **Validation Accounts** (owner-approved outreach/CRM/ads/payment access — `paid_hold`) — no module. This is the sole declared source for M8 and M10, and **neither M8 nor M10 has a calculator module either** — they are unimplemented at both the source and formula layer, not merely unscored.

### Built but never activated
- **Brave Search** (`discovery/brave.py`) — a real, complete 386-line adapter with a real `urllib` transport and budget gating exists, but no credential (`MASK_BRAVE_API_KEY`-style entry) is present in `.env.official.local` and `operational_status: paid_hold` keeps it disabled. Never executed against real candidates.

---

## Answers to the audit brief's numbered questions

**1. Registered but never executed for real data:** Google Places, Reddit, Firmographics, Validation Accounts (no code exists — stronger than "never executed," it's "never implementable under current code"); Brave Search (code exists, never credentialed/run); Google Ads (code exists to the transport boundary, never executable past it). BEA was executed once, but never in its registered per-market M1/M4 role.

**2. Collected but never processed into structured extraction:** BLS, SEC EDGAR, SAM.gov, USAspending (all real raw records, zero downstream parsers); Common Crawl pricing pages (real fetched HTML, explicitly "not wired into `evidence.services.CollectionService` or any `MethodExecutor`" per the module's own docs).

**3. Processed but never scored:** O\*NET task statements (become M3 scaffolding, every quantitative field stays null); Capterra pain mentions (real, grounded, but zero downstream method run postdates them); HVAC's own M2 pain clusters (all land as size-1 outliers, M2 never reaches COMPLETE even though 2 of 9 mentions get reused piecemeal by M4 and M9).

**4. Scored but omitted from any real report:** none found with confidence — every source that ever contributed a real weighted score component is also named in at least one generated report. Common Crawl pricing is the closest candidate, but it was never scored either (falls under Q2/Q3, not Q4).

**5. Duplicated evidence:** Jobber pricing is captured twice (Common Crawl archived copy vs. live Capterra review text) but these are complementary (pricing vs. sentiment), not contradictory duplicates. Jobber-as-named-competitor legitimately recurs across 3 real markets (Landscaping, Site Preparation Contractors, Janitorial Services) — the project's own Capterra extraction script explicitly documents and mitigates the double-counting risk by tagging each review to only one primary market, a real, code-level acknowledgment of the risk, though the mitigation lives inside one script's convention, not an enforced system-wide dedup rule.

**6. Sources that do not support their claimed measurement:** Common Crawl vendor pages supply list price, never true customer-paid price (a categorical mismatch for M4, a legitimate but recency-limited proxy for M5); O\*NET supplies task taxonomy, never frequency/duration/failure metrics (categorical mismatch for M3, unfixable by more O\*NET volume); Meta Ad Library manual checks can observe ad presence, not ad spend or conversion (a reasonable fit for "advertiser count," a poor fit for "buyer accessibility" more broadly).

**7. Missing high-value source families, mapped to exact missing fields:**
- **Reddit** → a second independent `source_family` for `PainMention` evidence, needed to clear `pain_intelligence`'s own `M2_MIN_SOURCE_FAMILIES = 3` threshold, which currently blocks PROVISIONAL/COMPLETE status project-wide regardless of volume.
- **Google Places reviews of target-market businesses** (not software vendors) → `M7Inputs.accounts_with_economic_buyer` / `.accounts_with_valid_reachable_channel` numerators, and critically `target_accounts` denominators — currently sourced from only 4-6 manually browsed homepages per market.
- **A firmographic data provider** → `M7Inputs.target_accounts` (the ratio denominator for both M7 percentage components — currently has no real automated source anywhere in the codebase) and employee-band verification (M7's missing schema field, `CURRENT_SYSTEM_AUDIT.md` §4 item 11).
- **BBB complaints / Indeed / Glassdoor (employer-side)** → `WorkflowStepEvidence.labor_burden` / `.failure_rate` — precisely the two component types O\*NET cannot supply, keeping M3 permanently unknown.
- **A real customer-spend source, at the `Observed`/`Interview Confirmed` tier (buyer survey, interview panel, billing-data partnership, or a genuine customer self-report found in already-collected text)** → `M4Inputs.annual_existing_paid_spend_usd`. **Corrected 2026-09-18:** the original draft characterized this field as having *no* desk-research path at all — too absolute. `M4Inputs.annual_existing_paid_spend_usd` is a generic `SourcedMetric` (`method_metrics/contracts.py:100`) that accepts any evidence-backed value tagged `Observed`/`Estimated`/`Interview Confirmed` per `docs/RESEARCH_METHODOLOGY.md`'s own M4 rule — it is not restricted to a specific evidence type. Three real, unexplored `Estimated`-tier paths exist today: (a) the already-collected Common Crawl vendor list-price data, usable if explicitly labeled `Estimated` (not `Observed`) rather than mis-targeted as this session's script did; (b) public-vendor SEC/investor disclosures for at least one already-named, publicly-traded competitor (Procore, NYSE: PCOR); (c) published third-party industry-pricing-survey benchmarks, a source class not yet attempted. A direct check of this session's 32 collected Capterra review texts for a genuine customer self-reported spend figure found none (only an unrelated "$9/month" reference to a different tool) — so no `Observed`-tier evidence currently exists in hand, but the check itself had never been performed before this pass, and a real `Observed`-tier path (a customer explicitly stating what they pay, in a review or interview) is not structurally impossible, only currently empty-handed. Only `Interview Confirmed`/receipt-level verified spend genuinely requires M8 primary research.

**8. Sources requiring real payment/approval:** Google Ads (approved developer token, transport still unbuilt); Google Places, Brave Search, Firmographics, Validation Accounts (all `paid_hold`); Reddit and Meta Ad Library (`approval_pending`, account/API approval rather than necessarily payment).

---

## Verified facts vs. inferred risks vs. could-not-verify

**[VERIFIED]:** Only M1 and M9 (HVAC only) have ever produced a complete, scored result across every method-result artifact opened in this audit. Common Crawl pricing data postdates every generated report and appears in none of them. Capterra has zero registry footprint. Google Ads' transport is a bare, unimplemented `Protocol`. `docs/YOUTUBE_DATA.md`'s "no live call" status line is stale/contradicted by real usage. The Capterra extraction script crashed on a real, unhandled `BudgetLimitExceeded` exception during this very audit.

**[INFERRED]:** "Never executed" for Google Places/Reddit/Firmographics/Validation Accounts is inferred from the complete absence of any adapter module — a stronger absence than a missing run folder, but still technically an inference that no undiscovered code path exists elsewhere in the repo.

**[COULD NOT VERIFY]:** Whether the M5 background process (still running at the time this document was written) will add competitor pricing evidence for the remaining 9 Phase 3 markets that changes any conclusion above — check `outputs/runs/phase3_m5_competitors/phase3_m5_results.json` for the current state when reading this. Whether any undiscovered script outside `scripts/` (e.g., inside an untracked/temp location) calls `market_scoring` or `reporting/` against real data — only the versioned `scripts/` tree was exhaustively searched.
