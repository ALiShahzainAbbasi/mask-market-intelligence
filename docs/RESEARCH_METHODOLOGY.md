# Research Methodology

Status: Phase 0 canonical specification  
Scope: ten-method market selection methodology

## 1. Methodology contract

Every candidate market is evaluated under the same versioned research protocol. Collection scope, taxonomies, scoring configuration, confidence rules, and gate criteria are recorded on each score snapshot. A market may have preliminary and full assessments, but comparisons must use compatible profiles.

The six layers must remain separate:

1. **Raw evidence:** what the source or participant actually said or reported.
2. **Extracted signal:** a structured, reviewable interpretation.
3. **Aggregate finding:** a pattern across signals, including dissent.
4. **Score:** deterministic application of an approved rubric.
5. **Judgement:** a human approval or documented override.
6. **Behavior:** observed buyer actions in experiments and sales.

## 2. Automation modes

| Mode | Meaning |
| --- | --- |
| Automated | Collection/derivation can run without case-by-case judgement, subject to policy and tests |
| AI-assisted | An LLM may produce structured proposals that remain traceable and reviewable |
| Semi-automated | Code aggregates or checks data; a human validates material interpretation |
| Human-owned | An accountable person supplies or approves the assessment |

An LLM never assigns a methodology score, overall score, confidence score, rank, gate result, or veto disposition.

## 3. Method summary

| ID | Method | Overall weight | Core question | Primary mode |
| --- | --- | ---: | --- | --- |
| M1 | Quantitative Market Analysis | 10% | Is there a sufficiently large, attractive, serviceable buyer pool? | Semi-automated |
| M2 | Sentiment & Pain Analysis | 15% | Is pain frequent, severe, economic, urgent, and commercially actionable? | AI-assisted + review |
| M3 | Workflow & Bottleneck Analysis | 15% | Where does work fail, wait, or consume costly manual effort? | Semi-automated |
| M4 | Economic Pain & Existing Spend | 15% | Is there measurable value and budget to solve the problem? | Semi-automated |
| M5 | Competitive Intelligence | 10% | What alternatives exist, how well do they solve the problem, and where are the gaps? | AI-assisted + review |
| M6 | Search & Buying Intent | 8% | Are buyers expressing problem, commercial, or switching intent? | Semi-automated |
| M7 | Buyer Accessibility & Channel Fit | 8% | Can enough economic buyers be identified and reached economically? | Human + measured data |
| M8 | Primary Customer Research | 10% | Do target buyers confirm the desk-research claims and willingness to act? | Human-owned + AI-assisted |
| M9 | MASK AI & Productization Fit | 5% | Can MASK AI deliver a standardized, defensible, recurring solution? | Leadership-owned |
| M10 | Real-World Market Validation | 4% | Do buyers take measurable actions at viable acquisition and delivery economics? | Behavioral measurement |

## 4. Method definitions

### M1 — Quantitative Market Analysis

**Required evidence:** company/establishment counts, company-size distribution, revenue bands or buyer economics, growth, geographic concentration, fragmentation, and estimated serviceable businesses. Record geography, period, population definition, source, units, and whether a value is observed or estimated.

**Outputs:** serviceable buyer-pool estimate, buyer economics, growth, fragmentation, geographic attractiveness, uncertainty, contradictions, and source lineage.

**Automation:** APIs and CSV/Excel uploads may normalize metrics. Deterministic code applies approved units, transforms, and the configurable proposed subweights in `SCORING.md`. Researchers approve mapping and estimates.

**Human responsibility:** validate market boundaries, company-band filters, estimation assumptions, and source suitability. Unknown values remain unknown.

### M2 — Sentiment & Pain Analysis

**Required evidence:** relevant operator/customer/vendor discussions or approved datasets, with persona kept distinct. Extract pain category, description, sentiment, severity, urgency, economic impact, purchase intent, workaround, dissatisfaction, AI suitability, evidence span, and extraction confidence.

**Outputs:** pain mentions and semantic clusters; frequency, severity, economics, intent, dissatisfaction, source/persona distribution, trends, representative evidence, and contradictions.

**Automation:** code performs relevance routing, normalization, embeddings, clustering, aggregation, and the configurable opportunity formula. AI proposes relevance, persona, structured pain fields, and cluster names. Humans review samples and material clusters.

**Human responsibility:** prevent persona mixing, validate cluster meaning, inspect outliers/contradictions, and approve score inputs. Sentiment and severity remain separate.

### M3 — Workflow & Bottleneck Analysis

**Required evidence:** workflow steps with role, system, input/output, frequency, handling time, manual effort, waiting time, failure rate, consequence, workaround, automation potential, estimated value, and evidence confidence.

**Outputs:** validated workflow maps, bottlenecks, affected roles, quantified consequences, automation candidates, and unresolved assumptions.

**Automation:** AI may propose workflows from evidence; deterministic code may calculate volumes, elapsed time, failure costs, and completeness. Workflow meaning and estimates are human-validated through primary research.

**Human responsibility:** own the workflow map and confirm it with target operators. No unvalidated AI-generated workflow supports a high-confidence score.

### M4 — Economic Pain & Existing Spend

**Required evidence:** salaries/headcount, outsourcing/BPO/agencies, SaaS/consulting spend, wasted advertising, revenue leakage, rework, downtime, management overhead, and current workarounds. Every numeric input is `Observed`, `Estimated`, `Interview Confirmed`, or `Unknown`.

**Outputs:** current annual cost, estimated revenue leakage, current service/software spend, recoverable percentage, proposed solution cost, potential economic value, value-to-price ratio, payback, and annual net benefit.

**Automation:** deterministic ROI calculations only. AI may extract explicitly stated values and context but cannot invent missing numbers.

**Human responsibility:** approve assumptions, ranges, recoverability, and comparability. Unknowns are surfaced as gaps rather than imputed invisibly.

### M5 — Competitive Intelligence

**Required evidence:** competitors and alternatives across Direct AI Vendor, Vertical SaaS, Agency, Consultancy, BPO, and Internal/DIY. Capture target market/buyer, problem, pricing status, features, integrations, positioning, case studies, reviews, complaints, strengths, weaknesses, and source evidence.

**Outputs:** landscape, substitutes, price and positioning ranges, capability gaps, switching friction, saturation, and contradictory signals.

**Automation:** collection and structured extraction may be assisted. AI may summarize cited material. Pricing is labelled `Exact`, `Starting at`, `Estimated`, or `Unknown`; absent pricing is never invented.

**Human responsibility:** verify material competitors, pricing labels, and whether a dominant platform already solves the target problem.

### M6 — Search & Buying Intent

**Required evidence:** keyword, country, date, source, volume, trend, CPC, competition, and intent classification: Problem, Informational, Solution, Commercial, Comparison, Transactional, or Competitor/Switching.

**Outputs:** total, commercial, transactional, and switching demand; rising keywords; solution awareness; data coverage; and platform/source caveats.

**Automation:** imports/APIs normalize metrics and deterministic code aggregates them. AI may propose intent labels; labelled evaluations and human review govern acceptance.

**Human responsibility:** validate ambiguous queries, geographic relevance, seasonality, and normalization. Search volume is not treated as purchase behavior.

### M7 — Buyer Accessibility & Channel Fit

**Required evidence:** economic buyer, operational champion, technical and procurement stakeholders; target-account count; identifiable buyers; contact-data availability; sales-cycle estimate; procurement complexity; channel diversity; and evidence for Email, Phone, LinkedIn, Meta, Google Search, Associations, Communities, Events, and Partnerships.

**Outputs:** reachable buyer pool, viable channels, expected friction, procurement risk, and acquisition hypotheses.

**Automation:** code calculates measured coverage and channel metrics. Researchers and sales own stakeholder mapping and channel feasibility.

**Human responsibility:** verify legal/compliant access and whether buyers can be reached economically. An unreachable buyer can become a critical veto.

### M8 — Primary Customer Research

**Required evidence:** interview metadata, participant role and market fit, transcript/notes, consent/access classification, and findings for pain confirmations/rejections, urgency, spend, workflows, authority, objections, current solutions, willingness to solve, and contradictions.

**Outputs:** desk-research confirmation rate, disagreement flags, role-stratified findings, saturation/coverage, and unresolved questions.

**Automation:** AI may extract a reviewable draft from transcripts and contrast interviews with desk research. It does not decide confirmation or score the method.

**Human responsibility:** conduct and qualify interviews, verify extracted findings, protect sensitive data, and approve conclusions.

### M9 — MASK AI & Productization Fit

**Required evidence:** Technical Fit, Integration Fit, Delivery Complexity, Standardization, Recurring Revenue, Proof Potential, and Expansion Potential. High assessments require written evidence, such as target-platform concentration with available integrations.

**Outputs:** delivery model, integration assumptions, standardizable core, bespoke burden, proof path, recurring/expansion potential, and technical risks.

**Automation:** code records rubrics and checks completeness. Assessment is owned by technical and business leadership; AI may organize evidence only.

**Human responsibility:** sign off feasibility, delivery economics, security/regulatory constraints, and evidence for high ratings.

### M10 — Real-World Market Validation

**Required evidence:** experiments with market, channel, offer, message, dates, spend, audience, impressions, clicks, leads, qualified leads, meetings, opportunities, proposals, sales, revenue, and gross profit.

**Outputs:** CTR, CPL, cost per qualified lead, cost per meeting, opportunity and close rates, CAC, Revenue/CAC, Gross Profit/CAC, sales cycle, pricing response, paid pilots, retention, and expansion signals where available.

**Automation:** deterministic code calculates all funnel and unit-economic metrics. Manual entry/import is the MVP; integrations come later.

**Human responsibility:** define qualified outcomes, validate attribution/data quality, interpret experiment design, and approve the behavioral conclusion.

## 5. Shared evidence requirements

Each finding records market, method, claim, polarity (`supporting`, `contradictory`, `neutral`), source or interview, verbatim context, source date, extraction/reviewer state, quality, and confidence inputs. Aggregates disclose sample size, distinct-source count, persona distribution, date range, rejected/duplicate counts, and contradictory evidence.

Evidence cannot support multiple claims invisibly: every use is an explicit link. Corrections supersede prior interpretations but do not erase them.

## 6. Research profiles by gate

| Gate | Required scope |
| --- | --- |
| Gate 1 — Broad Screen | M1, M2, M4, M5, M6, M7, and a documented light M9 |
| Gate 2 — Deep Research | Gate 1 plus full M3, expanded M2/M4/M5, M8 interviews, and full M9 |
| Gate 3 — Live Validation | Gate 2 plus M10 behavioral experiments and stronger acquisition/pricing evidence |
| Gate 4 — Final Selection | All methods, with paid-pilot/pricing/CAC/sales-friction/gross-margin/productization/retention/expansion evidence |

The gate engine also applies the exact thresholds, confidence requirements, completeness rules, and veto behavior in `SCORING.md`.

## 7. Method rubric status

The approved overall method weights are frozen in `SCORING.md`. The brief provides proposed internal formulas for M1 and M2 only. Subcriteria for M3–M10 are defined above, but numerical subweights are intentionally not invented in Phase 0. A computed score for one of those methods remains unavailable until leadership approves a versioned deterministic rubric. A reviewer may record a manual reviewed score with evidence and rationale; the UI must label it `manual rubric pending`, and cross-market comparison must disclose that status.
