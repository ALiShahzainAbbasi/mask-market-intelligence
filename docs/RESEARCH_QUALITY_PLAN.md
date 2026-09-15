# Research Quality Plan — Making Reports Conclusive

Status: owner-directed operating plan, 2026-09-16. Scope: the manual,
owner-directed research and reporting practice this project actually runs
today (Stage A/B market discovery, the two-report DOCX deliverables) — not
`mask_api.modules.reporting`'s separate offline JSON/HTML/CSV renderer
(see `docs/REPORTING.md`), which is unrelated infrastructure.

This document exists because two real problems surfaced in Stage B:

1. **Evidence volume was too thin to be conclusive.** Wave B's 15-candidate
   sample found real pain in 2 of 24 markets; Phase 3's first 5 markets at
   200 candidates found 2-11 real mentions each — real, but not enough to
   claim a pain theme is *common* rather than merely *present*.
2. **Reports presented thin evidence as a flat list, not a structured
   finding.** Individual real quotes were shown one row per mention with no
   frequency/clustering view, so a reader could not tell "1 anecdote" from
   "a recurring pattern" at a glance.

Both are fixed by the plan below, not by buying paid data sources (see the
2026-09-16 chat discussion: free/desk research had not been exhausted, and
the M8/M10 real-money step is deliberately sequenced last, only for
narrowed finalists).

## 1. The funnel: match evidence depth to how many markets are still alive

Never run full deep-dive depth across a wide candidate set again. Depth
scales up only as the candidate count scales down:

| Stage | Candidates | Real depth | Real cost | Status |
|---|---|---|---|---|
| Wave A | 40 | Census only (M1-light) | $0, ~10 API calls | Done |
| Wave B | 24 | 2 queries, 15 Gemini candidates/market | $0, ~1 day quota | Done — correctly too thin, and reported as such |
| Phase 3 (current) | 14 | 6 queries, 200 candidates/market | $0, ~3-5 days quota | In progress (5/14 done) |
| **Phase 3.5 (new)** | **top 5-6 of the 14** | **13 queries, 500-600+ candidates/market (HVAC parity)** | **$0, ~4-6 days quota** | Not started |
| Finalist pass | top 2-3 | + M4 completion (Common Crawl pricing), M7 full manual pass, M6 (Google Ads, first real paid step) | Small real cost | Not started |
| Validation | top 1-2 | M8 (real, budget-capped interviews) and/or M10 (real, budget-capped ad test) | Real, capped money | Held by design (A18-A20) |

Rule: **do not skip a narrowing step to save time.** Every stage exists to
avoid spending the next stage's cost on a market that won't survive it.

## 2. Evidence-strength standard (stop conflating "found" with "common")

Every real theme reported from here on must carry an explicit strength
label, computed from the real sample, never asserted by feel:

- **Anecdotal** — 1 real mention.
- **Emerging** — 2-3 real mentions, same theme.
- **Recurring** — 4+ real mentions, same theme, out of a stated sample size.
- **Established** — a real, non-outlier cluster the actual scoring formula
  (`PainIntelligenceService`) accepted (i.e., M2 reaches COMPLETE, not
  UNKNOWN). This is the only tier allowed to be called "conclusive."

A report may never say a pain "exists in this market" without one of these
four labels attached, and always with its real denominator ("4 of 11 real
mentions reviewed", not "4 mentions").

## 3. Report structuring standard (applies to every future Technical + Founder pair)

Replace flat per-mention quote lists with a **grouped theme table** as the
primary view, keeping the flat table as a technical appendix only:

- **Theme Frequency Table** (new, required, both reports): group real
  mentions by `pain_category` (or a merged category where two raw labels
  clearly describe the same real theme), show count/denominator, strength
  label (Section 2), mean severity/AI-suitability where available, and one
  representative real quote.
- The flat per-mention table (current format) stays in the **Technical**
  report only, as the full audit trail.
- The **Founder** report leads with the Theme Frequency Table, not
  individual quotes — a founder should see "3 of 11 = pricing/quoting
  friction (Emerging)" before any single quote.
- Every composite/partial/observed score must restate its real coverage %
  and sample size next to it, every time it appears — never a bare number.

## 4. Source completion backlog (cheap, no new paid tools required)

- **M4 — register the Jobber pricing-page SourcePolicy** (`docs/SCRAPING_POLICY.md`
  §4) so Common Crawl can retrieve real existing-paid-spend evidence. This
  is process work, not a purchase — do it before deciding M4 needs a paid
  source.
- **M2/M3/M9 collection scripts — persist raw evidence at collection time.**
  `discover_wave_b_top24.py` and `discover_phase3_deep_dive.py` only
  checkpoint aggregate counts; recovering real quotes required a separate
  cache-mining script (`extract_phase3_real_quotes.py`) after the fact.
  Future collection scripts must write `comments.json` and
  `pain_mentions.json` per market during the run itself (matching the
  original `collect_youtube_pain_evidence_us_hvac_10_99.py` /
  `extract_m2_pain_us_hvac_10_99.py` pattern), so this rework is never
  needed again.
- **M6 — Google Ads Keyword Planner.** The only source in this backlog
  that is genuinely paid/gated. Do not pursue until a market reaches the
  finalist pass (top 2-3), per Section 1's funnel.
- **M7 — full manual buyer-accessibility pass** (Meta Ad Library + company
  homepage checks) for every finalist, matching the depth already done for
  `us_hvac_10_99`. Free, but time-intensive — reserve for finalists only.

## 5. Standing rules this plan does not change

- **Two-report rule stays in force** (`feedback_two_report_requirement`
  memory): every market/stage still gets a separate Technical Evidence and
  Founder Decision report, automatically, no exceptions. This plan adds
  structure requirements (Section 3) on top of that rule, not a
  replacement for it.
- **Never force a canonical score.** Evidence-strength labels (Section 2)
  are an addition to, not a substitute for, the existing UNKNOWN/PARTIAL/
  Observed-Signal scoring discipline already in place.
- **No paid API/data purchase before a market reaches the finalist pass**
  (Section 1), per the 2026-09-16 owner discussion — the risk of picking
  the wrong market is reduced by narrowing before spending, not by
  spending before narrowing.

## 6. Immediate next actions

1. Let Phase 3 (current, lite-depth) finish its remaining 9 markets on
   quota reset — this is the narrowing step, not the final answer.
2. Once all 14 are in, select the real top 5-6 by combined evidence
   (Census + whatever pain/automation-fit signal Phase 3 found) and run
   **Phase 3.5** (HVAC-parity depth) on only those.
3. Retrofit the Theme Frequency Table (Section 3) into the existing 5
   interim Phase 3 reports and into all future reports from this point on.
4. Register the Jobber Common Crawl source policy (Section 4) — cheap,
   unblocks a real M4 data point regardless of which market wins.
