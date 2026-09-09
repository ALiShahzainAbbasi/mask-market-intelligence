# Method metrics module rules

Read the root `AGENTS.md`, `progress.txt`, `docs/RESEARCH_METHODOLOGY.md`,
`docs/SCORING.md`, `docs/AUTONOMOUS_RESEARCH_MODE.md`, `docs/COST_CONTROL.md`,
`docs/MODULARITY.md`, `docs/OFFICIAL_DATA.md`, and `docs/SEARCH_INTENT.md`
before changing this module.

- This module turns already-normalized, explicitly available source values into
  the exact v1 M1/M4/M5/M6/M7 scores. It does not fetch, parse, or discover
  evidence; `official_data`, `search_intent`, and analyst/manual capture remain
  the source adapters. Keep that boundary: no network, database, or provider
  imports here.
- Every raw input is a `SourcedMetric` with explicit provenance (source,
  observation state, geography, population, period, currency, unit, evidence
  reference). A missing metric stays `None`; never invent, default to zero, or
  silently substitute a different population/geography/period/currency.
- One calculator file per method (`m1.py`, `m4.py`, `m5.py`, `m6.py`, `m7.py`).
  Each validates that the loaded `MethodFormula` still has the exact v1
  component set and `weighted_sum` aggregation before using it, so a future
  formula-version drift fails loudly instead of silently miscalculating.
- Component transforms live only in `transforms.py` and call
  `mask_api.modules.scoring.math`; do not reimplement `linear`/`log_scale`/etc.,
  and do not copy component weights into prompts, UI, or provider adapters.
- Never renormalize the weighted sum around a missing component. A missing
  required component keeps the whole method `unknown`; the v1 partial-
  completeness rules (M1's "at least three of four" optional components) are
  the only approved exception, and even then only present components are
  weighted at their configured (not redistributed) weight.
- `M1`/`M5`/`M6` use `sample`/partial-completeness thresholds and can be
  `provisional`; `M4`/`M7` have no such rule in v1 and are strictly
  `unknown`/`complete`. Do not invent a provisional state a method's formula
  configuration does not define.
- Duplicate competitor-gap findings (same `competitor_id`) are rejected before
  they can inflate M5's `unresolved_gap`; do not weaken that check to "allow
  and dedupe" without an explicit methodology decision.
- Tests use fixture `SourcedMetric`/`M5CompetitorGap` values loaded against the
  real `configs/formulas/v1.yaml`, never live official-data or search-intent
  calls.
