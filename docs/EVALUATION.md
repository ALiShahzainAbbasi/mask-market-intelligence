# Testing and AI Evaluation Specification

Status: Phase 0 canonical specification

## 1. Objective

The system must demonstrate that deterministic calculations are correct and reproducible, collectors preserve evidence reliably, and AI extractions are sufficiently accurate against human-labelled data before they influence research decisions.

Evaluation is versioned. A prompt, model, schema, taxonomy, preprocessing, embedding, clustering, or post-processing change triggers the affected suite. Historical analysis remains tied to the version that produced it.

## 2. Test layers

| Layer | Required coverage |
| --- | --- |
| Unit | Normalization, calculations, weights, confidence, gaps, gates, vetoes, permissions, schema validation |
| Property/invariant | Weight sums, bounds, missing values, idempotency, reproducibility, no duplicate inflation |
| Parser fixture | Every collector: representative, empty, malformed, changed-layout, pagination, duplicate, policy/error cases |
| Integration | API/database, migrations, PostgreSQL queue/Windows worker, object storage boundary, Postgres/pgvector |
| Contract | OpenAPI/Pydantic/TypeScript compatibility; job and normalized-document contracts |
| AI evaluation | Labelled extraction data, slices, regression comparison, schema/span validity |
| Clustering evaluation | Human judgement of coherence, separation, duplicates/outliers, stability |
| Security | Tenant isolation, roles, upload validation, secret/log leakage, prompt-injection resistance |
| End-to-end | Evidence ingestion -> review -> deterministic score -> gate decision with lineage drill-down |

## 3. Gold-standard data

Begin M2 evaluation with **100–200 representative records**, manually labelled for:

- relevance;
- persona when discernible;
- pain presence/category;
- sentiment;
- severity;
- purchase intent;
- evidence spans and key commercial-pain fields.

The dataset must represent target sources, markets, personas, text lengths, clear/ambiguous/no-pain cases, contradictions, sarcasm/negation where encountered, duplicates, and difficult boundary cases. It must not consist only of easy examples or one industry.

Later method-specific sets cover search intent, competitor facts/pricing, interviews, general evidence polarity, and workflow/economic extraction.

### Labelling protocol

- Write a label guide with definitions and examples before bulk labelling.
- Use at least two independent annotators for a stratified overlap of at least 20%.
- Resolve disagreements through an adjudicator; retain individual and adjudicated labels.
- Track annotator role, label-guide version, timestamp, and adjudication reason.
- Measure inter-annotator agreement to distinguish model errors from ambiguous policy.
- Restricted transcripts remain in an access-controlled evaluation set; sanitized public fixtures are used in ordinary tests.

## 4. Dataset split and leakage control

Freeze document/group-aware train/development/test partitions. Near duplicates, threads, and excerpts from the same original source belong to the same partition. Use the development split for prompt/taxonomy iteration; the held-out test split is evaluated only for release candidates. Maintain a separate challenge set for regressions and prompt injection.

Do not optimize on the final test set. Add new production failures to a future versioned challenge/regression set, not retroactively to a reported release result.

## 5. Metrics

### Required AI metrics

| Task | Primary metrics | Additional diagnostics |
| --- | --- | --- |
| Relevance | Per-class precision/recall/F1, macro F1 | Irrelevant false-positive and relevant false-negative rates |
| Pain presence | Precision, recall, F1 | Errors by persona/source/market |
| Pain category | Macro F1, agreement | Confusion matrix; hierarchical partial match if taxonomy supports it |
| Sentiment | Accuracy and macro F1 | Adjacent-error rate; confusion matrix |
| Severity | Mean absolute error | % within 1 and 2 points; bias |
| Purchase intent | Weighted kappa and macro F1 | Overstatement rate, especially predicted 3–4 |
| Persona | Macro F1 | Unknown rate and unsupported inference rate |
| Evidence span | Exact/overlap F1 and valid-substring rate | Unsupported-claim rate |
| Schema | Valid-output rate | Repair rate and terminal failures |
| Competitor facts/pricing | Field precision/recall | Invented price/fact rate |
| Interview findings | Finding precision/recall and span support | Contradiction miss rate |

Always report sample counts and 95% bootstrap confidence intervals where the sample permits. Report overall and sliced results; a large easy slice must not hide failure for owners, interviews, transactional intent, or a particular source.

### Deterministic system metrics

- Exact expected values for every scoring example and boundary.
- Confidence mapping at 0, 49.999999, 50, 74.999999, 75, and 100.
- Gate results for missing, passing, failing, and vetoed scenarios.
- Identical input/configuration produces an identical calculation and input hash.
- Missing evidence stays null; no implicit renormalization.
- Duplicates cannot increase frequency, adequacy, or agreement.
- Historical snapshots remain unchanged after configuration updates.

## 6. Initial engineering release gates

The supplied business methodology does not prescribe model-quality thresholds. The following are **initial engineering safety gates**, versioned and subject to approval during calibration; lowering one requires a documented risk acceptance:

| Check | Initial gate |
| --- | ---: |
| Structured-schema valid without repair | >= 98% |
| Evidence span is a valid substring/offset | 100% for accepted records |
| Relevance macro F1 | >= 0.80 |
| Relevance irrelevant false-positive rate | <= 10% |
| Pain presence precision and recall | each >= 0.80 |
| Pain category macro F1 | >= 0.70 |
| Sentiment macro F1 | >= 0.75 |
| Severity MAE | <= 1.5 points |
| Purchase-intent weighted kappa | >= 0.70 |
| Unsupported material claim rate | <= 2% |
| Invented competitor pricing/financial amount | 0 accepted cases |

An aggregate pass is insufficient when a critical slice has materially unsafe performance. Before pilot use, reviewers must inspect every false high purchase-intent prediction, invented value, and unsupported material claim.

If a task misses its gate, its output can be shown as experimental/proposed but cannot automatically enter deterministic scoring. The system falls back to human entry/review.

## 7. Clustering evaluation

For representative markets, human reviewers evaluate:

- pairwise/co-membership agreement on a labelled subset;
- cluster purity/coherence and separation;
- duplicate dominance and persona mixing;
- outlier handling;
- stability across fixed-seed runs and small sample changes;
- usefulness and fidelity of AI-proposed names.

Quantitative metrics such as adjusted Rand index, normalized mutual information, silhouette score, or pairwise F1 may support evaluation when gold clusters exist. They do not replace reviewer assessment of commercial meaning. Approve algorithm/model/threshold parameters as a versioned clustering configuration.

## 8. Calibration study

After the 3–5-market technical pilot, research about 10 diverse markets under the same protocol. Compare computed, researcher, and reviewer scores and inspect systematic errors by method and source.

Examples to test:

- severity consistently overestimated;
- consumer-facing search volume unfairly dominates B2B markets;
- source repetition inflates pain frequency;
- estimates receive too much economic weight;
- low-accessibility markets appear attractive until outreach.

Adjust normalization or rubrics to improve fair evidence interpretation, never to make a preferred market win. Any calibration change creates a new configuration and triggers backtesting/recalculation for fair comparison.

## 9. Evaluation artifacts

Each evaluation run stores:

- code commit and environment;
- dataset/label-guide/split versions and hashes;
- prompt/model/schema/taxonomy/preprocessing versions;
- metric definitions and thresholds;
- overall and slice metrics with counts;
- confusion matrices/error samples;
- baseline comparison and statistically meaningful changes;
- pass/fail/risk-acceptance decision and approver;
- cost, latency, and schema/repair rates.

The command `make eval-ai` runs the reproducible offline suite without requiring unrestricted production data. Provider-dependent runs require explicit credentials/environment and must not leak secrets.

## 10. Regression and release process

1. Run unit, parser, integration, lint, and type checks.
2. Run the relevant development evaluation during iteration.
3. Freeze the release-candidate tuple.
4. Run held-out and challenge sets once.
5. Compare against the currently approved version and thresholds.
6. Review critical errors and slice regressions.
7. Approve, reject, or risk-accept with rationale.
8. Deploy as a new analysis version and temporarily increase review sampling.
9. Monitor drift, schema failures, reviewer corrections, source mix, and cost.

Rollback stops new runs on the bad version; it does not erase results. Affected records are marked/superseded by a later re-analysis.

## 11. Phase-level acceptance

- Every scoring function has unit and boundary tests.
- Every collector has offline parser fixtures and policy behavior tests.
- Every schema has valid/invalid fixtures and exact span checks.
- Every migration upgrades a clean database and the supported previous state.
- Critical workflows have integration and end-to-end lineage tests.
- Tests demonstrate tenant isolation and human approval/override requirements.
- No phase is complete while relevant tests, lint, types, migrations, or documentation fail.
