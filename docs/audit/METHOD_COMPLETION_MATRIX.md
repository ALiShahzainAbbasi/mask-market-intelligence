# Method Completion Matrix — 15 Markets × 10 Methods

**Date:** 2026-09-17, finalized 2026-09-18. All values below are **[VERIFIED]** by direct inspection of the named JSON run artifacts unless marked otherwise — no value is transcribed from progress.txt narrative alone without cross-checking against the underlying artifact where one exists. M5's snapshot reflects the live background process's on-disk state at time of writing (5 of 14 markets complete, a 6th in progress, confirmed still running and unchanged as of the 2026-09-18 finalization pass); see `SOURCE_UTILIZATION_REGISTER.md` for the full chain per source.

**Two notes carried over from `CURRENT_SYSTEM_AUDIT.md` §9 (2026-09-18 verification pass), applicable throughout this matrix:** (1) HVAC's M1=COMPLETE figure is real and well-evidenced but, unlike M9's, has no persisted, machine-verifiable result artifact on disk (`scripts/run_census_m1.py` never writes its result to JSON) — it is reconstructed from raw Census query responses plus narrative documentation, all mutually consistent, but on a different evidentiary footing than M9's directly-inspectable `m9_result.json`. (2) This matrix does not include any Capterra-derived evidence in any cell, which is correct and unchanged by the verification pass — that data was never wired into any score, and per the new compliance finding in `CURRENT_SYSTEM_AUDIT.md` §9.1, it should not be, until the owner resolves an unauthorized-collection concern (Capterra's own Terms of Use, independent of robots.txt, prohibit the automated collection and AI-processing method that was used).

## Legend

- **COMPLETE** — real, formula-compliant score, all required components available
- **PARTIAL** — some formula components available, real weighted contribution exists, but status is formally `unknown`/`provisional` per the calculator's own completeness gate
- **UNKNOWN** — calculator ran, required component(s) missing, `score=null` (this is the correct, honest output of a working calculator given insufficient evidence — not a crash)
- **LIGHT/PROXY** — a deliberately non-canonical, cheaper substitute score exists (explicitly labeled as such in the data), the canonical formula has never been run
- **NOT_CALCULATED** — no grounded records existed to even attempt a component build
- **SKIPPED (no occupation)** — M3-specific: no clean O\*NET occupation match exists for this NAICS code
- **NOT_STARTED** — no run of any kind exists; method is honestly absent, not faked
- **N/A (by design)** — Gate-deferred, human-owned method with a hardcoded non-inference short-circuit (M8/M10 with `validation.enabled=False`)

## Markets covered (15, per audit brief §8 instruction — none eliminated)

`us_hvac_10_99` (pilot/baseline) plus the 14 Phase 3 shortlist markets: 238210 Electrical Contractors, 561730 Landscaping Services, 238910 Site Preparation Contractors, 238290 Other Building Equipment Contractors, 561720 Janitorial Services, 561621 Security Systems Services, 811121 Automotive Body/Paint/Interior Repair, 238990 All Other Specialty Trade Contractors, 561210 Facilities Support Services, 811192 Car Washes, 541519 Other Computer Related Services, 812910 Pet Care Services, 561710 Exterminating and Pest Control Services, 238160 Roofing Contractors.

---

## Summary table

| Market | M1 | M2 | M3 | M4 | M5 | M6 | M7 | M8 | M9 | M10 |
|---|---|---|---|---|---|---|---|---|---|---|
| **HVAC (canonical baseline)** | **COMPLETE 6.34** | UNKNOWN (9 mentions) | UNKNOWN (30/30 steps, 0 components) | UNKNOWN (1/4 avail.) | UNKNOWN (2/5 avail.) | UNKNOWN (0/5) | UNKNOWN (4/6 avail.) | NOT_STARTED | **COMPLETE 6.476** | NOT_STARTED |
| Electrical Contractors (238210) | LIGHT 6.01 | UNKNOWN (10 mentions) | UNKNOWN (21/21 steps, 0 comp.) | LIGHT/UNKNOWN | NOT_CALCULATED (0 competitors) | NOT_STARTED | UNKNOWN (4/6 avail., real M7 run exists) | NOT_STARTED | PROXY 7.00 (n=6) | NOT_STARTED |
| Landscaping Services (561730) | LIGHT 5.06 | UNKNOWN (11 mentions) | UNKNOWN | LIGHT/UNKNOWN | UNKNOWN (3 competitors: jobber, markate, yardbook) | NOT_STARTED | UNKNOWN (real M7 run exists) | NOT_STARTED | PROXY 7.00 (n=3) | NOT_STARTED |
| Site Preparation Contractors (238910) | LIGHT 4.68 | UNKNOWN (2 mentions) | UNKNOWN | LIGHT/UNKNOWN | UNKNOWN (5 competitors: jobber, quickbooks, shackleton, stack, workiz) | NOT_STARTED | NOT_STARTED (m7-lite sample=6, no full run) | NOT_STARTED | PROXY 5.00 (n=1) | NOT_STARTED |
| Other Building Equipment Contractors (238290) | LIGHT 4.60 | UNKNOWN (6 mentions) | UNKNOWN | UNKNOWN | UNKNOWN (11 competitors) | NOT_STARTED | NOT_STARTED (sample=6) | NOT_STARTED | UNKNOWN (n=0, no mentions w/ field) | NOT_STARTED |
| Janitorial Services (561720) | LIGHT 4.55 | UNKNOWN (6 mentions) | UNKNOWN | LIGHT/UNKNOWN | UNKNOWN (1 competitor: jobber) | NOT_STARTED | NOT_STARTED (sample=6) | NOT_STARTED | PROXY 1.00 (n=2) | NOT_STARTED |
| Security Systems Services (561621) | LIGHT 3.96 | UNKNOWN (4 mentions) | UNKNOWN | LIGHT/UNKNOWN | **IN PROGRESS** (live at audit time, 2+ competitors seen) | NOT_STARTED | NOT_STARTED (sample=6) | NOT_STARTED | PROXY 5.00 (n=1) | NOT_STARTED |
| Automotive Body/Paint/Interior Repair (811121) | LIGHT 3.95 | UNKNOWN (0 mentions) | UNKNOWN | UNKNOWN | PENDING (not yet reached by live M5 run) | NOT_STARTED | NOT_STARTED (sample=7) | NOT_STARTED | UNKNOWN (n=0) | NOT_STARTED |
| All Other Specialty Trade Contractors (238990) | LIGHT 3.86 | UNKNOWN (5 mentions) | **SKIPPED (no occupation)** | LIGHT/UNKNOWN | PENDING | NOT_STARTED | NOT_STARTED (sample=5) | NOT_STARTED | PROXY 8.00 (n=1) | NOT_STARTED |
| Facilities Support Services (561210) | LIGHT 3.83 | UNKNOWN (0 mentions) | UNKNOWN | UNKNOWN | PENDING | NOT_STARTED | NOT_STARTED (sample=7) | NOT_STARTED | UNKNOWN (n=0) | NOT_STARTED |
| Car Washes (811192) | LIGHT 3.79 | UNKNOWN (1 mention) | **SKIPPED (no occupation)** | UNKNOWN | PENDING | NOT_STARTED | NOT_STARTED (sample=5) | NOT_STARTED | PROXY 10.00 (n=1) | NOT_STARTED |
| Other Computer Related Services (541519) | LIGHT 3.78 | UNKNOWN (2 mentions) | UNKNOWN | LIGHT/UNKNOWN | PENDING | NOT_STARTED | NOT_STARTED (sample=5) | NOT_STARTED | PROXY 7.00 (n=1) | NOT_STARTED |
| Pet Care Services (812910) | LIGHT 3.76 | UNKNOWN (0 mentions) | UNKNOWN | UNKNOWN | PENDING | NOT_STARTED | NOT_STARTED (sample=6) | NOT_STARTED | UNKNOWN (n=0) | NOT_STARTED |
| Exterminating and Pest Control Services (561710) | LIGHT 3.72 | UNKNOWN (0 mentions, but note: raw M2 recovery script found 1 mention) | UNKNOWN | UNKNOWN | PENDING | NOT_STARTED | UNKNOWN (real M7 run exists) | NOT_STARTED | UNKNOWN (n=0 in master; a real M9 run exists separately) | NOT_STARTED |
| Roofing Contractors (238160) | LIGHT 3.65 | UNKNOWN (3 mentions) | UNKNOWN | LIGHT/UNKNOWN | PENDING | NOT_STARTED | UNKNOWN (real M7 run exists) | NOT_STARTED | PROXY 6.00 (n=3) | NOT_STARTED |

**Reading note on the "LIGHT" M1/M4 cells:** these are not the canonical calculator outputs. `m1_light` is a different formula (see `CURRENT_SYSTEM_AUDIT.md` §3.3); `m4_light` is the `mean_purchase_intent_0_4`-only proxy inside `phase3_master.json`, not a run of `method_metrics/m4.py`'s full 4-component formula (which, per its own completeness gate, would also resolve UNKNOWN given the same underlying thin evidence). No Phase 3 market has ever had `method_metrics/m4.py`, `m5.py`, or `m6.py` run against it directly, in canonical form — the phase3_m5_competitors.py script does call the real `calculate_m5()`, which is why M5 shows a genuine (if `UNKNOWN`) calculator status rather than "LIGHT."

---

## Per-market detail

### HVAC (`us_hvac_10_99`) — the canonical baseline

The only market in the project to have gone through the full, canonical M1–M7/M9 pipeline (M8/M10 correctly deferred). This is real depth: 13 YouTube queries, 112 videos, 1,409 comments, 600 sent to Gemini for M2; 4-6 companies manually verified for M7; a real capability-registry mapping for M9.

- **M1 = COMPLETE, 6.34/10.** All 5 components OBSERVED, single source (Census CBP), zero AI involvement, fully reproducible from 9 real API queries. Confidence: high (deterministic, authoritative federal source). **Research complete / Decision-ready for this component.**
- **M2 = UNKNOWN.** 9 real grounded pain mentions from 422 Gemini-accepted / 600 sent / 1,409 collected comments. All 9 land in size-1 "outlier" clusters (`m2.no_non_outlier_cluster`) — below the min_cluster_size=2 threshold, compounded by the lexical (non-semantic) embedding provider. Missing: enough same-topic mentions to form a real cluster. Root cause: **Data shortage** (primary) + **Methodology limitation** (lexical embeddings suppress paraphrase clustering). Completion requires: either 10x+ more comment volume, or a semantic embedding upgrade, or both.
- **M3 = UNKNOWN.** 30/30 O*NET task statements for SOC 49-9021.00 grounded successfully (100% extraction success), but all 6 required components (`volume`, `labor_burden`, `failure_rate`, `business_consequence`, `automation_potential`, `manuality`) are `null` for every step. Root cause: **Source mismatch** — O*NET structurally cannot supply these fields for any occupation. Completion requires: human-owned primary research (M8-style interviews/observation), per the methodology's own design intent — not more O*NET calls.
- **M4 = UNKNOWN.** 1 of 4 components available (`commercial_intent`, from only 2 of 9 mentions with a purchase-intent field — self-labeled "THIN SAMPLE" in the run artifact). `annual_burden`, `existing_paid_spend`, `paid_workaround_penetration` all missing. Root cause: `existing_paid_spend` is **partially a Source mismatch** (no currently-configured source supplies true, `Observed`-tier buyer spend, and none was found by checking this session's own collected review text for a self-report) **and partially an unexploited opportunity** — `Estimated`-tier evidence (vendor list price with an explicit estimate label, or public-vendor SEC filings for at least one competitor) is legitimately usable today and was not attempted (corrected 2026-09-18, see `CURRENT_SYSTEM_AUDIT.md` §4 item 8); the other two components are **Data shortage**.
- **M5 = UNKNOWN.** 2 of 5 components available (`competitor_proof`: 7 real competitors from 9 mentions; `unresolved_gap`: real gap score 2.83 from 11 evidence spans with verbatim complaint quotes). `pricing_proof`, `differentiation_space`, `traction_proof` all missing. Root cause: `pricing_proof` is **Data shortage** (real Common Crawl pricing now exists but is not wired in — see `SOURCE_UTILIZATION_REGISTER.md`); `differentiation_space`/`traction_proof` are **Engineering failure** (no code path computes them anywhere in the project, for any market).
- **M6 = UNKNOWN.** 0 of 5 components. Zero evidence — not thin, zero. Root cause: **Access limitation** (no Google Ads developer token) + **Engineering failure** (no concrete transport implementation exists even if a token were obtained).
- **M7 = UNKNOWN.** 4 of 6 components available (`buyer_identification`, `contact_coverage`, `channel_diversity`, `meta_fit` — the last sourced via manual Meta Ad Library browsing, not the registered API). `sales_cycle_simplicity` and `procurement_simplicity` missing in every run. Root cause: **Data shortage** (no free source for sales-cycle/procurement data — genuinely needs primary/sales-process research). Secondary, unaddressed by any fix yet: sample is 4 of 6 companies (2 excluded, HTTP 403), and **no verification exists anywhere that any sampled company is actually in the 10-99 employee band** (schema has no field for it).
- **M8 = NOT_STARTED.** Correctly, honestly absent — no calculator module exists for M8 anywhere in the codebase, matching the Gate 2+ human-research design.
- **M9 = COMPLETE, 6.476/10.** All 7 components computed from the owner-supplied MASK AI Capability Registry (named CAP-IDs, PROVEN/DEMONSTRATED evidence tags) plus this market's real M2/M5 evidence (e.g., `integration_fit` cites the real, named competitor Jobber). The script explicitly flags itself for owner review before being treated as final. This is the only other real, canonical, complete score in the project besides HVAC's own M1. **Research complete for this component; not yet owner-reviewed/decision-ready per the script's own request.**
- **M10 = NOT_STARTED.** Correctly, honestly absent — no calculator module exists; Gate 3-deferred by design.

### Electrical Contractors (238210)

- **M1 (light) = 6.01/10**, non-canonical formula (see matrix note above). No canonical M1 run exists for this market.
- **M2 = UNKNOWN.** 10 real grounded mentions from 200 candidates sent (6-query, capped collection — an order of magnitude less query breadth than HVAC). Missing: enough same-topic mentions to cluster.
- **M3 = UNKNOWN.** Matched to O*NET-SOC 47-2111.00 (Electricians), 21/21 task statements grounded, same universal O*NET-field-absence pattern as HVAC.
- **M4 (light) = UNKNOWN.** `mean_purchase_intent_0_4 = 0.80` from 5 of 6 mentions with an intent field — this is a proxy value, not a run of the canonical 4-component `calculate_m4`.
- **M5 = NOT_CALCULATED.** Zero grounded competitor records extracted (real disposition counts: 74 accepted extractions, but zero yielded a usable competitor record — flagged `error: no real, grounded competitor records were extracted`). Distinct from every other Phase 3 market, which at least reaches `UNKNOWN` with some real competitor names.
- **M6 = NOT_STARTED.** No M6 run exists for this or any non-HVAC market.
- **M7 = UNKNOWN.** A real, full M7 run exists (`outputs/runs/m7_us_electrical_contractors_10_99_20260916T180740Z/`), 5 companies sampled, same 2-of-6-missing-components pattern as HVAC (`sales_cycle_simplicity`, `procurement_simplicity`). A real DOCX report pair exists for this market's M7 alone (`outputs/reports/m7/us_electrical_contractors_10_99_M7_*.docx`), explicitly scoped as M7-only, not a full market assessment.
- **M8/M10 = NOT_STARTED**, correctly.
- **M9 (proxy) = 7.00, n=6 mentions.** `PROXY_OBSERVED`, explicitly labeled not-the-real-M9 in its own data. No canonical M9 run exists for this market (would require the same owner-capability-registry mapping done for HVAC).

### Landscaping Services (561730)

- **M1 (light) = 5.06/10.**
- **M2 = UNKNOWN.** 11 real grounded mentions from 200 sent.
- **M3 = UNKNOWN.** Same O*NET-field-absence pattern (occupation match confirmed, exact SOC code not independently re-verified in this pass).
- **M4 (light) = UNKNOWN**, proxy only.
- **M5 = UNKNOWN.** 3 real, named competitors (jobber, markate, yardbook), with real weakness text for 2 of 3 (yardbook: "the integration with quickbooks was difficult"; markate: "built in 2005," "mobile interface is butt ugly"; jobber: no weakness captured). Still missing `pricing_proof`, `differentiation_space`, `traction_proof`.
- **M6 = NOT_STARTED.**
- **M7 = UNKNOWN.** Real, full M7 run exists (`outputs/runs/m7_us_landscaping_services_10_99_20260916T180746Z/`), 5 companies, same missing-component pattern. Real DOCX report pair exists (`outputs/reports/m7/us_landscaping_services_10_99_M7_*.docx`), M7-only scope.
- **M8/M10 = NOT_STARTED.**
- **M9 (proxy) = 7.00, n=3.**

### Site Preparation Contractors (238910)

- **M1 (light) = 4.68/10.**
- **M2 = UNKNOWN.** Only 2 real grounded mentions from 200 sent — one of the thinnest real M2 samples in the shortlist.
- **M3 = UNKNOWN.**
- **M4 (light) = UNKNOWN**, proxy only (n=1 mention with intent field).
- **M5 = UNKNOWN.** 5 real competitors (jobber, quickbooks, shackleton, stack, workiz) from the largest real candidate pool processed so far (541 candidates, vs. the 200-candidate cap used elsewhere — this market's real M5 pass was uncapped and took disproportionately long as a result, a known, disclosed scaling issue in `scripts/discover_phase3_m5_competitors.py`). One real weakness captured for jobber ("overrated garbadge," "sucks as a crm" — real verbatim quotes); none for the other 4.
- **M6 = NOT_STARTED.**
- **M7 = NOT_STARTED** as a full canonical run (only the light-tier `m7_buyer_accessibility` sample of 6 companies exists inside `phase3_master.json`, not a standalone `m7_result.json`).
- **M8/M10 = NOT_STARTED.**
- **M9 (proxy) = 5.00, n=1.** Single-mention proxy — very low evidentiary weight for a number that still feeds the composite ranking.

### Other Building Equipment Contractors (238290)

- **M1 (light) = 4.60/10.** Note: `observed_weight_0_1 = 0.30` here (vs. 0.40 for most other markets) — this market's composite is missing an additional component relative to its peers (M9-proxy resolved `UNKNOWN` here, not `PROXY_OBSERVED` — n=0 mentions carried an `ai_suitability_1_10` field).
- **M2 = UNKNOWN.** 6 real grounded mentions from 200 sent.
- **M3 = UNKNOWN.**
- **M4 = UNKNOWN** (uppercase status in this record — a real, minor schema inconsistency noted separately in `CURRENT_SYSTEM_AUDIT.md` §6).
- **M5 = UNKNOWN.** The largest real competitor set found anywhere in the project: 11 distinct names (accessconstruction, buildops, gohighlevel, procore, profitdig, shackleton, shackleton'saiagents, shackletonai, stack, workiz, workyard) — note `shackleton`/`shackletonai`/`shackleton'saiagents` are very likely the same real entity split into 3 near-duplicate keys by the name normalizer, a real data-quality issue on top of the sparsity. Weakness text captured for only 2 of 11 (buildops: "more service-dispatch than crew-based"; gohighlevel: "extremely difficult to use for beginner non tech ppl").
- **M6 = NOT_STARTED.**
- **M7 = NOT_STARTED** as a full canonical run (light-tier sample of 6 only).
- **M8/M10 = NOT_STARTED.**
- **M9 = UNKNOWN**, not even proxy-observed — zero mentions in this market's real extraction carried a usable `ai_suitability_1_10` value.

### Janitorial Services (561720)

- **M1 (light) = 4.55/10.**
- **M2 = UNKNOWN.** 6 real grounded mentions from 200 sent.
- **M3 = UNKNOWN.**
- **M4 (light) = UNKNOWN**, proxy only.
- **M5 = UNKNOWN.** 1 real competitor found (jobber), no weakness text captured. Thinnest real M5 result among the 5 markets the live background process has completed so far.
- **M6 = NOT_STARTED.**
- **M7 = NOT_STARTED** as a full canonical run (light-tier sample of 6 only).
- **M8/M10 = NOT_STARTED.**
- **M9 (proxy) = 1.00, n=2.** The lowest real AI-suitability proxy observed anywhere in the project — worth a specific note, since this pulls Janitorial Services to the bottom of the 14-market composite ranking (rank 14, composite 3.66) substantially because of this one component.

### Security Systems Services (561621)

- **M1 (light) = 3.96/10.**
- **M2 = UNKNOWN.** 4 real grounded mentions from 200 sent.
- **M3 = UNKNOWN.**
- **M4 (light) = UNKNOWN**, proxy only.
- **M5 = IN PROGRESS at time of writing.** The live background process (`scripts/discover_phase3_m5_competitors.py`) was actively processing this market's real YouTube/Gemini evidence when this audit was compiled (observed: 2 distinct competitors found through candidate 50 of a projected 513-candidate pool, several real Gemini-call timeouts logged and correctly handled). No final result exists yet — **[COULD NOT VERIFY]** final competitor list/status; will be available once the process completes.
- **M6 = NOT_STARTED.**
- **M7 = NOT_STARTED** as a full canonical run (light-tier sample of 6 only).
- **M8/M10 = NOT_STARTED.**
- **M9 (proxy) = 5.00, n=1.**

### Automotive Body, Paint, and Interior Repair and Maintenance (811121)

- **M1 (light) = 3.95/10.** Note: `observed_weight_0_1 = 0.30` — one fewer component populated than the 0.40-coverage markets.
- **M2 = UNKNOWN.** 0 real grounded mentions — the extraction pass ran but found no qualifying pain in this market's sampled comments.
- **M3 = UNKNOWN.**
- **M4 = UNKNOWN**, no light proxy available (no purchase-intent-bearing mentions exist, since M2 found none).
- **M5 = PENDING.** Not yet reached by the live M5 background process (queued behind Security Systems Services and 6 other markets).
- **M6 = NOT_STARTED.**
- **M7 = NOT_STARTED** as a full canonical run (light-tier sample of 7 only).
- **M8/M10 = NOT_STARTED.**
- **M9 = UNKNOWN.** No mentions carry an `ai_suitability_1_10` value (consequence of M2 finding zero mentions).

### All Other Specialty Trade Contractors (238990)

- **M1 (light) = 3.86/10.**
- **M2 = UNKNOWN.** 5 real grounded mentions from 200 sent.
- **M3 = SKIPPED (no occupation).** Honestly excluded — no single clean O*NET-SOC occupation match exists for this residual NAICS catch-all code; this was a deliberate, disclosed scoping decision, not a silent gap.
- **M4 (light) = UNKNOWN**, proxy only.
- **M5 = PENDING.**
- **M6 = NOT_STARTED.**
- **M7 = NOT_STARTED** as a full canonical run (light-tier sample of 5 only).
- **M8/M10 = NOT_STARTED.**
- **M9 (proxy) = 8.00, n=1.** Single-mention proxy, one of the highest observed — a market where the composite ranking is unusually sensitive to one anecdote.

### Facilities Support Services (561210)

- **M1 (light) = 3.83/10.** `observed_weight_0_1 = 0.30`.
- **M2 = UNKNOWN.** 0 real grounded mentions.
- **M3 = UNKNOWN.**
- **M4 = UNKNOWN**, no proxy available.
- **M5 = PENDING.**
- **M6 = NOT_STARTED.**
- **M7 = NOT_STARTED** as a full canonical run (light-tier sample of 7 only).
- **M8/M10 = NOT_STARTED.**
- **M9 = UNKNOWN.** No qualifying mentions.

### Car Washes (811192)

- **M1 (light) = 3.79/10.**
- **M2 = UNKNOWN.** Only 1 real grounded mention from 200 sent — the thinnest possible non-zero real evidence base in the shortlist.
- **M3 = SKIPPED (no occupation).** Honestly excluded, same reasoning as All Other Specialty Trade Contractors.
- **M4 = UNKNOWN** (real status recorded is uppercase in this record).
- **M5 = PENDING.**
- **M6 = NOT_STARTED.**
- **M7 = NOT_STARTED** as a full canonical run (light-tier sample of 5 only).
- **M8/M10 = NOT_STARTED.**
- **M9 (proxy) = 10.00, n=1.** The single highest AI-suitability proxy value found anywhere in the project — resting entirely on one Gemini-judged mention. This market ranks #3 overall (composite 5.34) and lands in "Tier 1 — Strong Candidate" in the generated Founder report substantially on the strength of this one data point. **This is the single clearest real illustration in the whole project of the composite-ranking risk flagged in `CURRENT_SYSTEM_AUDIT.md` §3.3.**

### Other Computer Related Services (541519)

- **M1 (light) = 3.78/10.** The one market in the 40-candidate universe outside the trades/field-service cluster (see `CURRENT_SYSTEM_AUDIT.md` §5). Its real Wave B evidence (n=1 mention, `ai_suitability_1_10=3`) pulled its Wave B composite down to rank 17 of 24, yet it was kept in the final 14 because the 24→14 cut reverted to Wave A's Census-only ranking (see `CURRENT_SYSTEM_AUDIT.md` §5). Note, corrected 2026-09-18: this market's Wave B evidence is not meaningfully thinner than Glass and Glazing Contractors' (also n=1 mention) — the earlier draft's framing of Glass and Glazing as a "stronger" excluded candidate did not survive verification; see `CURRENT_SYSTEM_AUDIT.md` §9.1.
- **M2 = UNKNOWN.** 2 real grounded mentions from 200 sent.
- **M3 = UNKNOWN.**
- **M4 (light) = UNKNOWN**, proxy only.
- **M5 = PENDING.**
- **M6 = NOT_STARTED.**
- **M7 = NOT_STARTED** as a full canonical run (light-tier sample of 5 only).
- **M8/M10 = NOT_STARTED.**
- **M9 (proxy) = 7.00, n=1.**

### Pet Care Services (except Veterinary) (812910)

- **M1 (light) = 3.76/10.** `observed_weight_0_1 = 0.30`.
- **M2 = UNKNOWN.** 0 real grounded mentions.
- **M3 = UNKNOWN.**
- **M4 = UNKNOWN**, no proxy available.
- **M5 = PENDING.**
- **M6 = NOT_STARTED.**
- **M7 = NOT_STARTED** as a full canonical run (light-tier sample of 6 only).
- **M8/M10 = NOT_STARTED.**
- **M9 = UNKNOWN.** No qualifying mentions.

### Exterminating and Pest Control Services (561710)

- **M1 (light) = 3.72/10.** `observed_weight_0_1 = 0.30`.
- **M2 = UNKNOWN in the master aggregation** (0 mentions recorded there) — but note a real, separately-run quote-recovery pass (`scripts/extract_phase3_real_quotes.py`) recovered 1 real grounded mention for this market from the underlying Gemini response cache, meaning the master aggregation's "0 mentions" figure understates what real evidence actually exists in the project's own cached artifacts. **This is a real, minor aggregation-completeness gap** — the master file was built before or independent of the later quote-recovery extension.
- **M3 = UNKNOWN.**
- **M4 = UNKNOWN.**
- **M5 = PENDING** in the live background process, but note this market also has an earlier, separate real M7 run (see below) — M5 and M7 pipelines have been run on different schedules for this market.
- **M6 = NOT_STARTED.**
- **M7 = UNKNOWN.** A real, full M7 run exists (`outputs/runs/m7_us_pest_control_10_99_20260916T181724Z/`), and a real DOCX report pair exists (`outputs/reports/phase3_m7/561710_exterminating_pest_control_services_M7_*.docx`), same missing-2-components pattern as every other real M7 run.
- **M8/M10 = NOT_STARTED.**
- **M9 = UNKNOWN** in the master aggregation (n=0) — same caveat as M2 above; a real M9-relevant mention may exist in the cache that the master file predates.

### Roofing Contractors (238160)

- **M1 (light) = 3.65/10.** The lowest `m1_light` score in the shortlist.
- **M2 = UNKNOWN.** 3 real grounded mentions from 200 sent.
- **M3 = UNKNOWN.**
- **M4 (light) = UNKNOWN**, proxy only.
- **M5 = PENDING.**
- **M6 = NOT_STARTED.**
- **M7 = UNKNOWN.** A real, full M7 run exists (`outputs/runs/m7_us_roofing_contractors_10_99_20260916T181729Z/`), and a real DOCX report pair exists (`outputs/reports/phase3_m7/238160_roofing_contractors_M7_*.docx`), same missing-2-components pattern.
- **M8/M10 = NOT_STARTED.**
- **M9 (proxy) = 6.00, n=3.**

---

## Cross-market patterns worth flagging explicitly

1. **Composite scores are highly sensitive to n=1 M9-proxy mentions.** Car Washes (n=1, proxy=10.00), All Other Specialty Trade Contractors (n=1, proxy=8.00), Site Preparation Contractors (n=1, proxy=5.00), Security Systems Services (n=1, proxy=5.00), Other Computer Related Services (n=1, proxy=7.00) — five of the fourteen markets have their M9-proxy component resting on a single Gemini judgment call, at real weight in the composite. This is the same risk identified in `CURRENT_SYSTEM_AUDIT.md` §3.3/§4 item 12, now shown concretely across the full matrix.
2. **No Phase 3 market has ever had a canonical M1, M4, M5, or M6 run** — only HVAC has. Every Phase 3 "M1"/"M4" figure is a light/proxy substitute.
3. **M3 is 12/12 UNKNOWN (with 2/14 honestly skipped) across every market attempted, plus the HVAC baseline (13/13 total)** — the most uniformly, structurally blocked method in the project.
4. **M7's real (non-light) runs exist for only 6 of 15 markets** (HVAC + Electrical + Landscaping + Pest Control + Roofing); the other 9 Phase 3 markets have only the light-tier 5-7-company sample embedded in `phase3_master.json`, not a standalone scored run.
5. **M6, M8, M10 are uniformly NOT_STARTED across all 15 markets** — no exceptions, no partial credit anywhere. This is honest and consistent, per `CURRENT_SYSTEM_AUDIT.md` §3.2's finding that M8/M10 deferral is by design, and §3.1's finding that M6 is structurally blocked project-wide.
