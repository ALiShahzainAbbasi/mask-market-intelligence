# Product Specification

Status: Phase 0 canonical specification  
System: MASK AI Market Intelligence & Selection System

## 1. Purpose

MASK AI needs a repeatable way to compare candidate markets using increasingly strong evidence rather than founder preference, anecdote, or one successful historical project. The product is an internal research operating system that collects and preserves evidence, converts it into reviewable signals, applies the same ten research methodologies to every market, and supports stage-gated selection.

The product must answer:

> Which market should MASK AI target, why, how confident are we, what evidence supports the conclusion, what contradicts it, and what still needs to be proven?

## 2. Product principles

1. **Evidence first.** A number without inspectable supporting and contradictory evidence is not a valid score.
2. **Separate layers.** Raw evidence, extracted signal, aggregate finding, deterministic score, human judgement, and buyer behavior are distinct records.
3. **Deterministic decisions.** LLMs assist interpretation; backend code calculates scores, rankings, confidence, completeness, and gates.
4. **Human accountability.** The system recommends; an authorized reviewer approves or overrides with a recorded rationale.
5. **Comparable research.** Markets use the same versions of collection rules, taxonomies, prompts, normalization, weights, confidence rules, and gate thresholds.
6. **Progressive proof.** Desk research narrows the field; interviews and live behavior must replace assumptions before final selection.

## 3. Users and responsibilities

| Role | Primary responsibilities | Important permissions |
| --- | --- | --- |
| Researcher | Create markets, plan research, ingest evidence, inspect AI output, prepare scorecards | Draft findings and submit reviews |
| Reviewer | Validate evidence, approve scores/confidence, resolve contradictions | Approve or reject scorecards; make documented overrides |
| Sales | Record outreach, buyer access, objections, and experiments | Edit assigned validation records |
| Technical | Assess integrations, feasibility, delivery complexity, and productization | Contribute to Method 9 assessments |
| Founder | Resolve critical vetoes and make final selection | Explicit, audited founder override |
| Admin | Manage organization, users, roles, source policies, and configuration | Configuration and access management |

One person may hold multiple roles, but approval events must identify the acting role and user. The application must support separation of researcher and reviewer when the organization chooses to enforce it.

## 4. Core workflow

1. Create a candidate market with submarket, geography, company band, likely buyer, owner, reviewer, and hypotheses.
2. Generate a versioned research plan from the current methodology configuration.
3. Collect or upload permitted source material.
4. Preserve raw content, normalize it, deduplicate it, and record collection provenance.
5. Classify relevance before expensive analysis.
6. Extract structured evidence, pains, personas, contradictions, and other methodology-specific signals.
7. Cluster related evidence while retaining links to every member and source.
8. Let researchers inspect raw context and correct or reject extracted signals.
9. Calculate methodology scores with deterministic, versioned rules where an approved rubric exists.
10. Let reviewers approve or adjust scores with evidence and rationale.
11. Calculate market score, confidence, evidence completeness, red flags, and stage-gate readiness.
12. Compare markets researched under compatible configurations.
13. Conduct primary research and live experiments as later gates require.
14. Select, hold, advance, or reject a market with an immutable decision record.

## 5. Research stages

| Stage | Purpose | Typical result |
| --- | --- | --- |
| Broad Screen | Apply economical desk research to 30–50 markets | Narrow to 10–15 |
| Deep Research | Validate workflows, economics, competition, interviews, and product fit | Narrow to about 5 |
| Live Validation | Test messages, channels, pricing, demos, and small paid experiments | Narrow to 2–3 |
| Finalist | Resolve unit economics, delivery, retention, and expansion evidence | Prepare final decision |
| Selected | Record the primary market and the evidence/configuration used | One selected market |
| Rejected | Preserve why a market failed or was vetoed | Reusable institutional memory |

`Hold` is a decision/status, not a research stage. A held market keeps its current stage and records the blocking evidence gap.

## 6. Required product capabilities

### 6.1 Market registry and workspace

- Create and edit market definitions and hypotheses.
- Assign owner and reviewer.
- Show stage, status, score, confidence, method completion, gaps, red flags, and next action.
- Start every market with an empty ten-method scorecard.

### 6.2 Evidence system

- Register source policies before collection.
- Support compliant automated collection and analyst uploads.
- Preserve raw and normalized content, metadata, content hash, source URL, and collection run.
- Detect exact duplicates and flag near duplicates.
- Browse, filter, and reverse-navigate from a score to the source context.
- Retain supportive, contradictory, neutral, and rejected evidence.

### 6.3 Intelligence modules

- Quantitative market data.
- Sentiment and commercial pain.
- Workflow and bottlenecks.
- Economic pain and existing spend.
- Competitive intelligence.
- Search and buying intent.
- Buyer accessibility and channel fit.
- Primary customer research.
- MASK AI and productization fit.
- Real-world market validation.

### 6.4 Review and scoring

- Display computed score, reviewed score, and confidence separately.
- Require evidence for scores and high-confidence claims.
- Record substantial score overrides with reviewer, rationale, evidence, and timestamp.
- Calculate weighted scores only in backend code from a versioned configuration.
- Refuse to present incomparable snapshots as a single fair ranking without a warning or recalculation.

### 6.5 Decisions and audit

- Detect deterministic evidence gaps and recommend the next research action.
- Evaluate stage gates and surface failed conditions.
- Prevent automatic advancement when a critical veto is open.
- Audit source, prompt, taxonomy, extraction, score, confidence, review, override, experiment, and stage changes.

## 7. Key views

- Market leaderboard with numeric scores, confidence, stage, completeness, and veto state.
- Market detail with Overview, Evidence, Pain, Market Data, Workflow, Economics, Competition, Search, Buyer, Interviews, Product Fit, Validation, and Scoring.
- Evidence explorer with source, persona, date, pain, method, evidence type, sentiment, and confidence filters.
- Pain intelligence with clusters, frequency, severity, economics, intent, source distribution, trends, and original evidence.
- Side-by-side market comparison for all ten methods; charts supplement rather than replace numbers.
- Evidence gaps showing proven, weak, missing, and the next required research action.

## 8. Success criteria

The system succeeds when MASK AI can enter multiple markets and produce a reviewable selection report containing:

- overall Market Opportunity Score and all ten methodology scores;
- score and confidence configuration versions;
- evidence, samples, sources, diversity, calculations, contradictions, and reviewer approvals;
- pain clusters, economics, workflows, competitor gaps, search demand, buyer accessibility, interviews, product fit, and validation behavior;
- red flags, missing evidence, recommended next experiment, and gate recommendation;
- a complete explanation of why any market advanced, was held, was rejected, or was selected.

Operational success also requires that repeated calculation from the same immutable inputs and configuration produces the same result.

## 9. MVP boundary

The first useful release targets Gate 1 and includes authentication, market registry, evidence storage, a common collector framework, two or three initial compliant collectors, pain extraction and clustering, manual quantitative/competitor/search inputs, manual reviewed method scores, deterministic weighted scoring, confidence, evidence drill-down, leaderboard, and Gate 1 logic.

The initial operating profile is the private Windows MVP in ADR 0003. It starts with 3 markets and 2 permitted collectors, uses manual evidence as a first-class path, and follows COST_CONTROL.md. Infrastructure scale and model volume are not product acceptance criteria; research validity, auditability, traceability, and honest incompleteness are.

Deferred: broad social scraping, every data API, autonomous workflow mapping, predictive success ML, Meta/CRM integrations, automated outreach/interviews, custom warehouse, complex multi-agent systems, and Kubernetes.

## 10. Product acceptance invariants

- No score can be approved without linked evidence or an explicit documented `insufficient evidence` state.
- No final ranking is generated by an LLM.
- No raw evidence is silently replaced by a summary or newer AI analysis.
- No critical veto is bypassed without a founder decision record.
- No market reaches `Selected` without Gate 4 evidence and an explicit human decision.
- Missing evidence is never silently treated as poor evidence or excluded to inflate a score.
