# Scoring, Confidence, Stage Gates, and Vetoes

Status: Phase 0 canonical specification  
Rule: all calculations are deterministic backend operations; no LLM calculates or approves a score.

## 1. Approved overall weights

| ID | Method | Weight |
| --- | --- | ---: |
| M1 | Quantitative Market Analysis | 10% |
| M2 | Sentiment & Pain Analysis | 15% |
| M3 | Workflow & Bottleneck Analysis | 15% |
| M4 | Economic Pain & Existing Spend | 15% |
| M5 | Competitive Intelligence | 10% |
| M6 | Search & Buying Intent | 8% |
| M7 | Buyer Accessibility & Channel Fit | 8% |
| M8 | Primary Customer Research | 10% |
| M9 | MASK AI & Productization Fit | 5% |
| M10 | Real-World Market Validation | 4% |
|  | **Total** | **100%** |

Default method scores use a 0–10 scale. The final approved Market Opportunity Score is:

```text
M1×0.10 + M2×0.15 + M3×0.15 + M4×0.15 + M5×0.10
+ M6×0.08 + M7×0.08 + M8×0.10 + M9×0.05 + M10×0.04
```

Weights are configurable only through a versioned scoring configuration. A change creates a new configuration; it never changes historical snapshots. A weight configuration must total exactly 1.000000 before activation.

## 2. Score states

For every market and method, store separately:

- **Computed score:** deterministic output from structured, eligible evidence and a versioned rubric. It may be `null` if the rubric or required inputs are incomplete.
- **Reviewed score:** human-approved value used by an approved snapshot. It may equal the computed score or be an evidenced override.
- **Suggested confidence:** deterministic 0–100 confidence output and mapped Low/Medium/High label.
- **Reviewed confidence:** optional human-approved adjustment with rationale and evidence.

A method record also stores input snapshot/hash, calculation breakdown, rubric version, evidence links, sample and source statistics, reviewer state, and timestamps.

### Override rule

Any reviewed score that differs from the computed score requires an override event. The default `substantial_override_delta` is configurable and initially **1.0 point** on the 0–10 scale. Every override—substantial or not—is recorded; a substantial one additionally requires a reviewer role, written rationale, at least one linked evidence item, and explicit approval. The threshold is an engineering control, not a methodology weight.

Scores outside 0–10 are invalid. Rounding is presentation-only: calculations retain at least six decimal places and the UI defaults to two.

## 3. Missing evidence and eligibility

- `Unknown`, missing, rejected, superseded, duplicate, or policy-blocked values are not silently imputed.
- Missing method scores are `null`, not zero. Zero means the rubric was completed and produced the lowest value.
- The overall ten-method score is `null` until all ten required reviewed method scores are approved under a compatible configuration.
- The UI may show a **provisional contribution** (sum of available weighted contributions) but must not label it the final score or rank it as though complete.
- Stage-gate scores require every method in that gate's profile. The engine does not renormalize around a missing required method.

## 4. Internal method calculations

### 4.1 M1 proposal

The brief proposes these configurable subweights:

| Component | Default subweight |
| --- | ---: |
| Serviceable buyer pool | 30% |
| Buyer economics | 25% |
| Growth | 15% |
| Fragmentation | 15% |
| Geographic attractiveness | 15% |

Each component must be normalized deterministically to 0–10 using a versioned transform whose units, caps, and boundary values are documented before activation. Until those transforms are approved, the formula is a proposal and the M1 computed score remains unavailable; reviewers can use an evidenced manual rubric.

### 4.2 M2 Pain Opportunity proposal

Normalize eligible cluster components to 0–10, then calculate:

```text
Pain Opportunity =
  Frequency × 0.25
+ Severity × 0.25
+ Economic Impact × 0.20
+ Purchase Intent × 0.15
+ Dissatisfaction × 0.15
```

Purchase intent is extracted on 0–4 and normalized by `value / 4 × 10`. Severity, economic impact, and dissatisfaction are already 1–10 when present. Frequency normalization, cluster-to-market aggregation, minimum sample requirements, and treatment of multiple mentions per document must be approved and versioned before the M2 computed score is enabled. The subweights are an implementation proposal, not a change to M2's overall 15% weight.

### 4.3 M3–M10

Phase 0 defines required criteria but has no approved numerical subweights from the supplied methodology. The system must not invent them. Each computed score stays `null` until an approved deterministic rubric is added to a scoring configuration. Manual reviewed scores remain possible only with evidence, a stated rubric, reviewer identity, and the `manual rubric pending` label.

## 5. Input scales

### Purchase intent

| Value | Meaning |
| ---: | --- |
| 0 | No buying intent |
| 1 | Problem aware |
| 2 | Looking for advice |
| 3 | Evaluating solutions/vendors |
| 4 | Actively purchasing/switching |

### Sentiment

| Value | Meaning |
| ---: | --- |
| -2 | Very negative |
| -1 | Negative |
| 0 | Neutral |
| +1 | Positive |
| +2 | Very positive |

Sentiment never substitutes for pain severity. A neutrally worded source may report severe economic pain.

### Numeric evidence provenance

Economic and quantitative values use `Observed`, `Estimated`, `Interview Confirmed`, or `Unknown`. Calculations may use estimates only when the rubric allows them and must expose sensitivity/range assumptions.

## 6. Confidence engine

The initial suggested-confidence formula is:

| Dimension | Weight |
| --- | ---: |
| Source diversity | 25% |
| Sample adequacy | 25% |
| Evidence quality | 20% |
| Recency | 10% |
| Cross-source agreement | 20% |

Each dimension is normalized by deterministic method-specific rules to 0–100. Those normalization rules and minimums are versioned alongside each method rubric. The weighted result maps to:

| Numeric confidence | Label |
| ---: | --- |
| 0–49.999999 | Low |
| 50–74.999999 | Medium |
| 75–100 | High |

Contradictions reduce cross-source agreement; they are not deleted. Repeated content from one source family does not count as source diversity. Near duplicates do not increase sample adequacy.

### Market/gate confidence

For a complete gate profile, calculate the weighted mean of required methods' numeric confidence using the approved overall method weights renormalized across that fixed gate profile. This renormalization is allowed only for confidence aggregation, not to conceal a missing score. Every required method must have confidence; otherwise gate confidence is unavailable.

For the final overall score, calculate confidence across all ten methods using the approved weights. A human confidence adjustment is stored separately and requires a rationale, reviewer, evidence, and timestamp.

## 7. Evidence completeness and next action

Completeness is not confidence and not score. Each method defines versioned required evidence checks with states:

- `Proven`: required evidence exists, is approved, and meets quality/minimum rules.
- `Weak`: some evidence exists but fails a quality, diversity, recency, or adequacy rule.
- `Missing`: no eligible evidence satisfies the requirement.
- `Not applicable`: permitted only when the rubric explicitly allows it and a reviewer approves the reason.

The gap engine orders deterministic next actions by: gate-blocking requirement, critical veto investigation, lowest-cost discriminating research, then lower-priority completeness. AI may explain the selected action but cannot choose it.

## 8. Gate score profiles

A gate score is calculated from that gate's fixed required method set after every required score is approved. It uses approved weights renormalized across the fixed set:

```text
gate_score = Σ(method_score × approved_weight) / Σ(required_method_weights)
```

This creates a comparable 0–10 gate score and does not renormalize around missing data.

| Gate | Required methods | Minimum score | Confidence | Additional requirements |
| --- | --- | ---: | --- | --- |
| Gate 1 — Broad Screen | M1, M2, M4, M5, M6, M7, light M9 | 6.0 | Displayed; no minimum specified | No open critical veto |
| Gate 2 — Deep Research | M1–M9, with full M3/M9, expanded M2/M4/M5, and M8 | 7.0 | At least Medium | All profile completeness checks pass; no open critical veto |
| Gate 3 — Live Validation | M1–M10 | 7.5 | Reported | Strong behavioral signals per approved M10 rubric; no open critical veto |
| Gate 4 — Final Selection | M1–M10 | Preferred 8.0 | High | Evidence for paid pilots, pricing, CAC, sales friction, gross margin, productization, retention, expansion; founder decision |

Gate 4's 8.0 is a preference in the supplied methodology, not an unconditional minimum. A selection below it requires an explicit founder override explaining why. Gate 3 cannot pass until “strong behavioral signals” is converted into an approved, versioned M10 rubric; until then the engine returns `not ready` rather than guessing.

### Gate result

The deterministic engine returns:

- `not_ready`: required scores, confidence, rubric, or evidence checks are incomplete;
- `blocked`: an open critical veto exists;
- `eligible_to_advance`: numerical and evidence conditions pass;
- `does_not_meet_gate`: completed conditions fail;
- `founder_review_required`: Gate 4 preference is missed or an authorized critical-veto exception is requested.

Humans record the actual decision: `advance`, `hold`, `reject`, or, at Gate 4, `select`. Eligibility never changes a market stage automatically.

## 9. Veto/red-flag engine

Initial veto taxonomy:

- no economic buyer;
- no meaningful budget;
- major regulatory or API barrier;
- unreachable buyer;
- highly bespoke delivery;
- dominant platform already solves the problem;
- no qualified buying intent.

Every red flag stores type, severity (`warning` or `critical`), status (`suspected`, `confirmed`, `resolved`, `accepted_exception`), evidence, owner, rationale, and timestamps. Only a `confirmed` critical veto blocks advancement. A `suspected` critical veto makes its investigation the next action and can keep a gate `not_ready` when the profile requires resolution.

An accepted exception requires founder identity, rationale, evidence, timestamp, affected gate, and expiry/review date. It does not erase the veto.

## 10. Snapshots, comparison, and reproducibility

A score snapshot is immutable and records market definition version, research profile, eligible evidence cutoff, scoring/rubric/confidence versions, computed and reviewed values, calculations, completeness, veto state, and approvals.

Markets may be ranked together only when snapshots use the same market-definition rules, research profile, scoring configuration, and comparable evidence cutoff policy. Otherwise the UI must recalculate under a common configuration or display a clear incompatibility warning.

Given identical eligible inputs and configuration, recalculation must be bit-for-bit stable except for an explicitly documented numeric precision boundary.
