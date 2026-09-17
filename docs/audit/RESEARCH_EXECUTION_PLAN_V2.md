# Research Execution Plan V2 — MASK AI Market Intelligence

**Date:** 2026-09-17, finalized 2026-09-18 after an independent verification pass (see `CURRENT_SYSTEM_AUDIT.md` §9 for the full list of corrections; items 0.5, 0.7 [new], 1.1, and 1.6 below reflect those corrections). Dependency-ordered. Priorities per the audit brief's own classification:
**P0** — Correctness: defects that invalidate calculations, evidence, or market comparisons.
**P1** — Essential evidence: missing research necessary for a meaningful desk-research decision.
**P2** — Decision validation: interviews, technical assessment, commercial evidence for finalists.
**P3** — Optional improvements: limited decision value.

All effort/cost estimates are engineering-time judgment calls by this audit, clearly labeled as estimates, not measured facts. Nothing in this plan authorizes starting large collection runs, paid APIs, or outreach — those remain owner decisions, flagged explicitly where they occur.

---

## Phase 0 (P0) — Fix defects that currently distort calculations or comparisons

These must land before any new market advances, and before any of the two currently-UNKNOWN-but-close methods (M2, M5) are trusted the moment they resolve to a real score.

### 0.1 — Fix M2's dormant status case-mismatch bug
- **Objective:** prevent a future real M2 COMPLETE result from being silently dropped from the Phase 3 composite.
- **Exact work:** `scripts/discover_phase3_deep_dive.py:464` — replace `m2_result.status.value == "COMPLETE"` with a comparison against the real lowercase `M2Status.COMPLETE` enum value (or, better, `m2_result.status == M2Status.COMPLETE` using the enum directly, avoiding string comparison entirely).
- **Files/modules affected:** `scripts/discover_phase3_deep_dive.py`.
- **Dependencies:** none — a one-line fix.
- **Effort/cost:** ~15 minutes engineering + a regression test.
- **Acceptance criteria:** a unit/integration test that constructs a real `M2Result` with `status=M2Status.COMPLETE` and asserts the composite calculation captures its score. Re-run against every cached Phase 3 market to confirm no output changes (expected, since none has hit COMPLETE yet) — this run itself is the regression check.
- **Expected output:** a merged fix; no change to any currently-published score, but the class of bug that already caused real wasted M5 quota (per `progress.txt`) is closed for M2 before it fires.

### 0.2 — Fix M2's denominator to count Gemini-accepted, not Gemini-sent, documents
- **Objective:** make `all_relevant_unique_documents` measure what its own name and `unknown_rule` text claim.
- **Exact work:** in `scripts/extract_m2_pain_us_hvac_10_99.py:262` and `scripts/discover_phase3_deep_dive.py:695`, replace `len(candidates)` with a count of documents whose grounding disposition was `ACCEPTED` (or, if the intent is "assessed," rename the field/its `unknown_rule` text to match reality instead).
- **Files/modules affected:** both scripts above; possibly `pain_intelligence/metrics.py`'s docstring for clarity.
- **Dependencies:** none.
- **Effort/cost:** ~1-2 hours (touches two scripts + needs a decision on which semantics is intended).
- **Acceptance criteria:** re-run the HVAC M2 extraction against the already-cached Gemini responses (no new API calls needed — reuse the pattern from `scripts/extract_phase3_real_quotes.py`, which already reads the cache without spending quota) and confirm the recomputed `all_relevant_unique_documents` = 422, not 600.
- **Expected output:** a corrected HVAC M2 result artifact; documented, one-line change to every Phase 3 market's M2 summary once similarly recomputed from cache.

### 0.3 — Implement M5's two structurally-dead formula components
- **Objective:** stop `differentiation_space` and `traction_proof` from being permanently `None` regardless of evidence volume.
- **Exact work:** in `scripts/discover_phase3_m5_competitors.py`, replace the hardcoded `median_offer_similarity_0_1=None` / `verified_reference_count=None` with real computation — e.g., `differentiation_space` from pairwise similarity of competitor feature/offer descriptions already captured in Gemini's competitor extraction; `traction_proof` from a countable proxy already available (e.g., distinct named reviewers/reference mentions across Capterra + YouTube evidence, once wired per 1.1 below).
- **Files/modules affected:** `scripts/discover_phase3_m5_competitors.py`; possibly a small addition to `method_metrics/m5.py`'s contract if a new evidence shape is needed.
- **Dependencies:** best sequenced after 1.1 (Capterra wiring) so `traction_proof` has real reference-count material to draw from.
- **Effort/cost:** ~1 day (design + implement + test two new component computations).
- **Acceptance criteria:** a market with sufficient competitor evidence (e.g., Other Building Equipment Contractors, 11 named competitors) produces non-`None` values for both components in a re-run; unit test asserting the formula can reach `COMPLETE` given a fully-populated `M5Inputs` fixture (currently no such test can pass, since the script itself never produces one).
- **Expected output:** M5 becomes capable of reaching COMPLETE for the first time in the project's history, for any market with sufficient real evidence.

### 0.4 — Fix the Capterra extraction script's retry/budget crash — **on hold, see 0.7**
- **Objective:** stop the script from crashing on `BudgetLimitExceeded` when retries push real request volume past the ledger's `max_requests`.
- **Exact work:** in `scripts/extract_phase3_capterra_pain.py`, either (a) catch `BudgetLimitExceeded` alongside `GeminiError` and treat it as a terminal, logged stop (not a crash), or (b) size `BudgetLedger(max_requests=...)` to account for `MAX_RETRYABLE_ATTEMPTS` per document up front, or (c) both.
- **Files/modules affected:** `scripts/extract_phase3_capterra_pain.py`.
- **Dependencies:** **superseded by 0.7 below, added 2026-09-18.** This crash fix remains a real, correctly-diagnosed engineering defect, but do not schedule or execute a re-run of this script until 0.7's authorization question is resolved — fixing the crash would otherwise just make it easier to resume a collection this audit's verification pass found is not currently authorized.
- **Effort/cost:** ~30 minutes (the fix itself is unchanged in scope; only its scheduling changed).
- **Acceptance criteria:** unchanged, but gated on 0.7.
- **Expected output:** deferred pending 0.7.

### 0.7 — Resolve the Capterra collection-authorization question before any further use — **new, added 2026-09-18**
- **Objective:** resolve, with owner (and ideally legal) input, whether this session's Capterra review data may be used at all, before any engineering effort is spent making its collection more reliable or wiring its output into scoring.
- **Exact work:** a 2026-09-18 verification pass found that Capterra's real, live Terms of Use (Section 10) explicitly prohibit both the automated/headless-browser collection method used and the subsequent use of that content with a generative AI system to "analyze... or evaluate" it — independent of and not overridden by Capterra's permissive robots.txt, which the clause names explicitly. Full clause text and citation in `CURRENT_SYSTEM_AUDIT.md` §9.1. The owner should choose one of: (a) seek Capterra's express written consent for this specific research use (the clause's own stated carve-out), (b) formally accept the risk of retaining/using data collected in violation of the terms, with legal sign-off, or (c) treat the existing raw files and extraction outputs as quarantined and unusable, and pursue a different evidence source for the gap this was meant to fill (real competitor weaknesses/reviews for M5).
- **Files/modules affected:** none technical yet — this is a decision, not an engineering task. If (c) is chosen, `scripts/extract_phase3_capterra_pain.py`, `scripts/register_and_fetch_jobber_pricing.py`-style Common Crawl scripts (which scrape vendor pricing pages directly, a different real-world/policy situation from a UGC review aggregator, but worth a parallel terms check per source before further reliance), and any future G2/Capterra/TrustRadius-style source should be re-scoped around a genuinely licensed or first-party data path (e.g., a vendor's own published case studies, or direct outreach with consent) instead.
- **Dependencies:** none — this can and should happen before any other Capterra-related work in this plan.
- **Effort/cost:** owner/legal decision time, unscheduled by this audit. No engineering effort until a direction is chosen.
- **Acceptance criteria:** an explicit, recorded owner decision (per option a/b/c above) exists before 0.4's crash fix is executed, before 1.1 wires any Capterra evidence into scoring, or before the script is run again in any form.
- **Expected output:** a documented, owner-approved resolution — this plan does not presume which one.

### 0.5 — Re-target Jobber/Workyard/Workiz pricing evidence from M4 to M5
- **Objective:** stop a vendor's advertised list price from being treated as M4's true-customer-spend field, and correctly wire it into M5's `pricing_proof` instead, where the methodology explicitly permits "Starting at"-labelled pricing.
- **Note on scope, added 2026-09-18:** this item is unaffected by 0.7's Capterra finding — Jobber/Workyard/Workiz pricing pages are each vendor's own public marketing content (a materially different legal posture from a third-party UGC review aggregator with an explicit anti-scraping/anti-AI clause), retrieved via Common Crawl's already-archived copy, not a live scrape of the vendor's own site. This audit did not perform a terms-of-service check on Common Crawl's own terms or on each vendor's site terms specifically — a quick check of both is cheap and worth doing before or alongside this item, given what the Capterra finding revealed about the value of checking terms explicitly rather than assuming.
- **Exact work:** update `scripts/register_and_fetch_jobber_pricing.py`'s docstring to remove the incorrect M4 claim; write a small integration step that maps the real Common Crawl pricing summaries (`outputs/runs/jobber_pricing_common_crawl/summary.json`, `outputs/runs/competitor_pricing_common_crawl/{workyard,workiz}/summary.json`) into `M5Inputs.pricing_proof` for the specific markets where each vendor is a real, named M5 competitor (Jobber → Landscaping Services, Site Preparation Contractors, Janitorial Services; Workyard/Workiz → Other Building Equipment Contractors / Site Preparation Contractors, per `phase3_m5_results.json`'s real competitor lists).
- **Files/modules affected:** `scripts/discover_phase3_m5_competitors.py` (or a new small wiring script), `scripts/register_and_fetch_jobber_pricing.py` (docstring correction only).
- **Dependencies:** 0.3 (M5 component implementation) should land first so there's a real formula path to receive this data.
- **Effort/cost:** ~half a day.
- **Acceptance criteria:** at least one Phase 3 market's M5 result shows `pricing_proof: available` with a real, cited Common Crawl source, for the first time in the project.
- **Expected output:** M4/M5 stop conflating list price with spend; M5 gets closer to COMPLETE for markets with named, priced competitors.

### 0.6 — Fix M1-light labeling in generated reports; reconcile the ranking-as-complete practice
- **Objective:** bring M1's disclosure discipline up to the same standard M2/M4/M9 already meet in generated reports; stop the Phase 3 master Founder report from ranking/tiering markets on a 30-40%-coverage composite without the caveat `docs/SCORING.md` requires.
- **Exact work:** (a) in the report-generation script (currently a scratchpad-only Node.js file, per `CURRENT_SYSTEM_AUDIT.md` §2.4 — this should itself be fixed as part of Phase 1, see 1.5), add "-light" to every `M1` occurrence in generated prose/tables; (b) **owner decision required** — either relabel the 14-market ranking as an explicitly provisional "screening order, not a score-complete ranking" throughout, or hold off on any Tier 1/2/3 strategic language until a market reaches a higher real coverage threshold. This audit does not choose for the owner; it flags the two options.
- **Files/modules affected:** report-generation script; `docs/SCORING.md` (if the owner approves formally documenting a "screening ranking" exception).
- **Dependencies:** none technical; owner sign-off needed for the labeling-standard decision.
- **Effort/cost:** ~2-3 hours for the mechanical relabeling; owner decision time is unscheduled.
- **Acceptance criteria:** re-generated `phase3_master` reports show "M1-light" consistently and either drop tier language or add an explicit "screening-only, not decision-grade" banner on the ranking table.
- **Expected output:** reports that cannot be misread as more certain than the evidence supports.

---

## Phase 1 (P1) — Essential evidence and integration work

### 1.1 — Wire this session's new Common Crawl pricing evidence into real scoring (Capterra excluded pending 0.7)
- **Objective:** stop real, already-collected, properly-authorized evidence from sitting unused.
- **Exact work:** extend `method_metrics/m5.py` consumption paths (or the driver scripts that construct their inputs) to read the Common Crawl pricing summaries, for the specific markets each is evidentially relevant to. **Corrected 2026-09-18: Capterra pain evidence is explicitly excluded from this item's scope.** Per 0.7, it must not be wired into any score until the owner resolves the collection-authorization question — including this one.
- **Files/modules affected:** `scripts/discover_phase3_m5_competitors.py` (or a new aggregation step), `scripts/aggregate_phase3_master.py`.
- **Dependencies:** 0.3, 0.5. (0.4/0.7 are no longer dependencies of this item, since Capterra evidence is out of scope here.)
- **Effort/cost:** ~1 day (reduced from the original estimate, which included Capterra wiring).
- **Acceptance criteria:** at least one Phase 3 market's `phase3_master.json` shows a non-empty, Common-Crawl-sourced `pricing_proof` contribution.
- **Expected output:** the first Phase 3 market with real Common Crawl pricing evidence wired into M5. If the owner resolves 0.7 favorably, a follow-up item (not numbered here, since it depends on an outcome this plan does not presume) would extend this same integration pattern to Capterra pain evidence.

### 1.2 — Let M5 finish for the remaining 9 Phase 3 markets; add a candidate-volume cap
- **Objective:** complete the in-progress M5 background pass without unbounded per-market runtime.
- **Exact work:** do not interrupt the currently-running process. Once it completes (or if it needs to be restarted), add a `MAX_CANDIDATES_PER_MARKET` cap (matching the 200-candidate cap already used for M2-light) to `scripts/discover_phase3_m5_competitors.py`, since the uncapped design let one market (Site Preparation Contractors) process 541 real candidates versus ~200-280 for others — a real, disclosed but unaddressed scaling inconsistency.
- **Files/modules affected:** `scripts/discover_phase3_m5_competitors.py`.
- **Dependencies:** none; can run in parallel with everything else in this plan.
- **Effort/cost:** ~2 hours for the cap; the collection itself is already running (real time cost: hours, driven by API rate limits, not engineering effort).
- **Acceptance criteria:** `phase3_m5_results.json` has an entry for all 14 markets; each market's candidate count is capped consistently.
- **Expected output:** a complete, comparable M5 competitor dataset across all 14 Phase 3 markets.

### 1.3 — Upgrade M2's embedding provider from lexical hashing to real semantic embeddings
- **Objective:** stop paraphrased-but-lexically-distinct pain statements from being mechanically prevented from clustering.
- **Exact work:** replace or augment `LocalHashingEmbeddingProvider` (`pain_intelligence/embeddings.py`) with a real semantic embedding call (a small local sentence-embedding model, or a low-cost hosted embeddings API if budget allows — **owner decision** on cost/vendor). Re-cluster existing cached mentions (no new collection needed) to see whether any latent clusters emerge from already-collected evidence before assuming more raw volume is the only lever.
- **Files/modules affected:** `pain_intelligence/embeddings.py`, `pain_intelligence/clustering.py` (threshold may need retuning for a different embedding space), new tests.
- **Dependencies:** none technical; a vendor/cost decision if a paid embeddings API is chosen (**flag for owner approval** — this audit does not authorize a new paid API).
- **Effort/cost:** ~2-3 days engineering; ongoing marginal cost if a paid provider is chosen (likely small — embeddings are cheap per call), $0 if a local model is used.
- **Acceptance criteria:** re-clustering the existing 9 real HVAC mentions (and the larger real Phase 3 mention sets) with the new provider is compared against the lexical-hashing baseline; report whether any non-outlier clusters newly form.
- **Expected output:** either genuine new M2 signal from *already-collected* evidence (best case, no new API spend needed), or confirmation that the real bottleneck is volume, not clustering method (a valuable negative result either way).

### 1.4 — Add employee-band verification to M7
- **Objective:** stop assuming, rather than confirming, that sampled companies are actually in the 10-99 employee band.
- **Exact work:** add an `employee_band_verified: bool` (or a confidence-scored estimate) field to `M7Inputs`/the sampling protocol; source it from whatever is cheaply available (LinkedIn company-size badges, About-page language, a firmographic lookup if 1.6 below is pursued). Until a real source exists, at minimum flag every existing M7 run's sample as "employee band unverified" in generated reports.
- **Files/modules affected:** `method_metrics/contracts.py` (`M7Inputs`), all `scripts/run_m7_us_*.py` scripts, report-generation script.
- **Dependencies:** best paired with 1.6 (firmographic source) for a real fix; the "add a disclosure flag now" half can ship immediately.
- **Effort/cost:** ~1 day for the disclosure-flag version; open-ended for a real verification source depending on which is chosen.
- **Acceptance criteria:** every M7 report explicitly states whether employee-band membership was verified or assumed, per company sampled.
- **Expected output:** an honest caveat added immediately; a real fix once a verification source exists.

### 1.5 — Consolidate the reporting pipeline
- **Objective:** stop generating real deliverables through a scratchpad-only, uncommitted Node.js script disconnected from the system's own specified `reporting`/`market_scoring` modules.
- **Exact work:** **owner decision required** on direction — either (a) commit the Node.js report-generation script into the repo proper (under `scripts/` or a new `tools/reporting/` directory) and have it read from `market_scoring.MarketScoreSnapshot`-shaped JSON (calling `market_scoring`/`confidence` for real, rather than each research script computing its own informal aggregate), or (b) invest in extending the existing Python `reporting/` module with a DOCX renderer and retire the Node.js path. Option (a) is likely lower-effort given the existing script already works and is used; option (b) better honors the original architecture. This audit flags the decision; it does not make it.
- **Files/modules affected:** either the Node.js script (formalized) or `apps/api/src/mask_api/modules/reporting/` (extended) + `market_scoring/` (actually invoked for the first time).
- **Dependencies:** none blocking; can proceed independently of other phases.
- **Effort/cost:** option (a): ~2-3 days (commit + wire through `market_scoring`). Option (b): ~1-2 weeks (build a DOCX renderer, achieve parity with the current Node.js output).
- **Acceptance criteria:** the next generated report pair is produced by a committed, tested script that calls the real scoring/confidence machinery rather than recomputing an informal aggregate inline.
- **Expected output:** every future report is structurally guaranteed to match what the canonical pipeline would compute, closing the gap identified in `CURRENT_SYSTEM_AUDIT.md` §2.4.

### 1.6 — Formalize the screening-weight configuration (versioning/documentation, not re-approval of the approach)
- **Objective — refined 2026-09-18, see `CURRENT_SYSTEM_AUDIT.md` §3.4 for the four-part correction this item is based on.** The two-wave screening *process* (Wave A, then Wave B, then narrow) was already discussed and agreed with the owner in chat (`progress.txt`, AUTONOMOUS-050/051) — this item does not need to re-litigate that. What remains genuinely open: (a) the *specific numeric weight values* were never separately surfaced for owner sign-off, (b) they are not versioned anywhere outside two Python scripts, and (c) no `docs/` file documents that a screening-weight scheme exists at all, separate from canonical v1.
- **Exact work:** add a `screening_weights_v1` (or similar) block to `configs/formulas/`, matching the values currently hardcoded in `discover_phase3_deep_dive.py`/`discover_wave_b_top24.py`; update both scripts to read from it; add a short cross-reference note to `docs/SCORING.md` or `docs/RESEARCH_METHODOLOGY.md` documenting that this scheme exists and is intentionally distinct from and subordinate to the canonical v1 formulas; get the owner's sign-off specifically on the numeric weight values themselves (narrower than "re-approve screening" — the screening approach is not in question).
- **Files/modules affected:** new `configs/formulas/` entry, both discovery scripts, `docs/SCORING.md` (cross-reference note).
- **Dependencies:** none technical; **owner sign-off needed on the specific weight values**, per the audit brief's instruction not to change methodology weights without approval — narrower in scope than re-approving the already-agreed screening process.
- **Effort/cost:** ~1 day engineering once the weight values are signed off.
- **Acceptance criteria:** the screening composite formula is reproducible from a versioned config file, not two independent hardcoded dicts, and is documented in at least one `docs/` file.
- **Expected output:** an approved, versioned, documented screening methodology, distinct from and clearly subordinate to the canonical v1 formulas.

### 1.7 — Market universe expansion / challenger screening
- **Objective:** directly address the confirmed structural bias toward HVAC's own sector (`CURRENT_SYSTEM_AUDIT.md` §5) before investing further deepening effort in the current 14+1.
- **Exact work:** define a second, independently-sourced candidate list (e.g., 15-20 markets) deliberately drawn from outside the 238/236/811/561/812 trades cluster — B2B SaaS-adjacent services, professional services, healthcare administration (non-clinical), logistics/e-commerce operations support, hospitality back-office — filtered only by MASK AI's actual stated capability constraints (not by resemblance to HVAC), then run the same Wave-A-style Census pre-screen against them. **Owner decision required** on scope/budget for this expansion — it is real, if modest, new work (Census pre-screening is $0/free-tier).
- **Files/modules affected:** a new `scripts/discover_candidate_markets_challenger.py` (parallel to the existing Wave A script, not a replacement), `configs/markets/` (if any advance to formal configuration).
- **Dependencies:** none technical; owner scope decision.
- **Effort/cost:** ~2-3 days engineering (reusing the existing Wave A pipeline design) + real Census API time (free, minutes).
- **Acceptance criteria:** a second, real, Census-grounded ranking exists for a genuinely different candidate universe, comparable in rigor to the original Wave A pass.
- **Expected output:** either confirmation that the trades cluster remains the strongest available candidate set even against real outside competition (strengthens confidence in the current 14), or discovery of a previously-excluded, stronger candidate (directly serves the project's stated goal of not favoring a predetermined industry).

### 1.8 — Google Ads: sequence the two independent blockers for M6
- **Objective:** make progress on M6 without waiting on a single combined blocker.
- **Exact work:** (a) engineering can start immediately, independent of credential status — implement a concrete class satisfying `GoogleAdsHistoricalMetricsTransport`, tested against fixtures (this needs no live credential to build or unit-test). (b) separately and in parallel, the **owner** pursues the Google Ads developer-token approval (already applied for, per the owner's own statement this session) — this is explicitly outside this audit's authority to act on (no paid APIs, no account actions).
- **Files/modules affected:** `apps/api/src/mask_api/modules/search_intent/google_ads.py`, new tests.
- **Dependencies:** transport engineering (a) has none; live use of it depends on (b), an owner-side action.
- **Effort/cost:** ~3-5 days for a real, tested transport implementation.
- **Acceptance criteria:** a concrete `GoogleAdsHistoricalMetricsTransport` implementation passes offline tests against realistic fixture responses; flipping `operational_status`/`enabled`/`policy_approved` to true (once the owner's credential lands) is the only remaining step to go live.
- **Expected output:** M6 becomes a credential-away, not a credential-and-engineering-away, problem — meaningfully de-risking Gate 1's currently-unreachable status (`CURRENT_SYSTEM_AUDIT.md` §3.1).

---

## Phase 2 (P2) — Decision validation (finalists only, human-owned)

**Owner decision required before this phase starts at all:** which markets are "finalists" and how many. Nothing below should begin until that selection is made, per the project's own documented Gate design.

### 2.1 — M8 primary customer research design + execution
- **Objective:** obtain real, human-sourced confirmation of desk-research pain/spend claims for finalist markets.
- **Exact work:** design an interview protocol (targeting the specific pains identified in each finalist's M2/M5 evidence); the owner or a designated researcher conducts real interviews; no calculator currently exists for M8 — one must be built (`method_metrics/m8.py`, following the M1-M9 pattern) once interview data has a defined schema.
- **Files/modules affected:** new `method_metrics/m8.py` and matching `contracts.py` additions; new `configs/formulas/v1.yaml` M8 subweights (currently intentionally unspecified pending this work, per `docs/RESEARCH_METHODOLOGY.md:166`).
- **Dependencies:** finalist selection; 0.1-0.6 and 1.1-1.7 substantially complete (no point interviewing about a market whose desk-research evidence is still buggy or unverified).
- **Effort/cost:** interview design ~2-3 days; execution is real human time (owner-estimated, not this audit's to project) — likely weeks, not days, for a handful of finalist markets.
- **Acceptance criteria:** real interview transcripts/notes exist, mapped to the same pain/spend claims M2/M4 made, with a documented confirm/refute outcome per claim.
- **Expected output:** the project's first real M8 score for at least one market.

### 2.2 — Full canonical M9 for finalists beyond HVAC
- **Objective:** replace the light AI-suitability proxy with a real, capability-registry-grounded M9 for any market advancing past screening.
- **Exact work:** repeat `scripts/run_m9_us_hvac_10_99.py`'s real methodology (owner capability registry + market-specific M2/M5 evidence) for each finalist, with explicit owner review before treating any result as final (matching the HVAC script's own stated request).
- **Files/modules affected:** a new `scripts/run_m9_us_<finalist>.py` per finalist, following the HVAC precedent.
- **Dependencies:** finalist selection; each finalist's M2/M5 evidence should be as complete as Phase 1 can make it first.
- **Effort/cost:** ~1 day per finalist market (reusing the HVAC script's structure) + owner review time.
- **Acceptance criteria:** each finalist has a real, complete M9 score with the same evidence-traceability standard as HVAC's.
- **Expected output:** genuine, comparable M9 scores across all finalists, not proxies.

### 2.3 — M10 behavioral validation design (top 1-2 markets only)
- **Objective:** measure real buyer behavior (landing-page signups, outreach response rates, a small paid pilot) rather than stated intent.
- **Exact work:** design and, with explicit owner approval, execute a small real-world test (e.g., a landing page + a modest, disclosed ad spend, or a limited outreach campaign) for the top 1-2 markets remaining after M8. **This phase item involves real spend, real outreach, and real external-facing action — entirely outside this audit's authority; flagged for owner decision and execution, not something this or any future audit session should initiate unilaterally.**
- **Files/modules affected:** no calculator exists for M10 either — same gap as M8, needs `method_metrics/m10.py` once a data shape is defined.
- **Dependencies:** 2.1, 2.2 complete; owner approval for spend/outreach.
- **Effort/cost:** real marketing/ops budget (owner-estimated); engineering effort for the calculator itself ~2-3 days once the real data shape is known.
- **Acceptance criteria:** real, measured buyer-behavior data exists for at least one market.
- **Expected output:** the project's first real M10 score — the final piece needed for a genuinely decision-grade recommendation.

---

## Phase 3 (P3) — Optional improvements

### 3.1 — Reddit as a second M2 source family
- **Objective:** clear `pain_intelligence`'s own `M2_MIN_SOURCE_FAMILIES = 3` threshold, currently unmet for every market.
- **Effort/cost:** ~3-5 days for a new adapter module, following `youtube_data`'s shape.
- **Acceptance criteria:** real Reddit-sourced pain mentions appear alongside YouTube/Capterra mentions for at least one market, tagged with a distinct `source_family`.

### 3.2 — Evaluation harness execution
- **Objective:** answer audit item 15 (no formal evaluation of extraction/clustering quality was found) with a real, run evaluation.
- **Exact work:** execute (or build, if genuinely absent) the harness `docs/EVALUATION.md` describes against a labeled sample of already-collected real evidence.
- **Effort/cost:** ~3-5 days, mostly labeling effort for a ground-truth sample.
- **Acceptance criteria:** a real precision/recall (or equivalent) number exists for the grounding/extraction pipeline, not just an architectural description of how evaluation *should* work.

### 3.3 — Cosmetic consistency fixes
- Standardize "not available" tokens (`unknown`/`UNKNOWN`/`PENDING`/`NOT_CALCULATED`/`n/a`) to one consistent, correctly-capitalized vocabulary across all generated reports.
- Fix the `aggregate_phase3_master.py:95` `or 0` sort-key pattern to an explicit `(value is not None, value)` tuple key.
- De-duplicate the near-identical `shackleton`/`shackletonai`/`shackleton'saiagents` competitor-name variants found in Other Building Equipment Contractors' M5 result.
- **Effort/cost:** under a day combined.

---

## Sequencing summary

```
Phase 0 (P0, ~1 week)         → must complete before trusting any new M2/M5 result
Phase 1 (P1, ~3-4 weeks,      → can mostly run in parallel; 1.7 (universe expansion)
  parallelizable)               should start early since it gates whether the current
                                 14+1 markets are even the right set to keep deepening
Phase 2 (P2, owner-paced)     → gated on finalist selection; involves real spend/outreach
                                 requiring explicit owner approval at each step
Phase 3 (P3, opportunistic)   → no hard dependency on anything above
```

**The single highest-leverage near-term action, in this audit's judgment:** Phase 0 items 0.1, 0.2, 0.3, 0.5, 0.6 (all engineering-only, no new evidence needed, ~1 week combined), plus 0.7 (an owner decision on Capterra, not engineering effort), plus 1.7 (market universe expansion, ~2-3 days, addresses the most consequential structural finding in this audit) should be addressed first. Together the engineering items cost under two weeks of effort and, along with the 0.7 decision, directly address the three findings most likely to currently mislead a real market-selection decision or expose the project to avoidable risk: (a) a 30-40%-coverage composite being read as a ranked recommendation, (b) a candidate universe that was never free to contain anything but HVAC's own neighborhood, and (c) a real, unresolved data-collection authorization question that must be settled — not worked around — before any of this session's Capterra evidence is touched again. (0.4's crash fix is explicitly deferred until 0.7 resolves, per the 2026-09-18 correction.)
