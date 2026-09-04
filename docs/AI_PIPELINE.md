# AI Processing Pipeline

Status: Phase 0 canonical specification

## 1. Boundary of responsibility

LLMs may:

- classify relevance, persona, intent, and evidence type;
- extract structured facts and evidence spans;
- summarize cited evidence and surface contradictions;
- assist taxonomy mapping;
- propose cluster names after deterministic/vector clustering;
- draft comparisons between desk research and interviews.

LLMs must not:

- calculate method or market scores, confidence, ranks, completeness, ROI, funnel metrics, or stage-gate results;
- approve their own output;
- invent numbers, prices, sources, quotes, participants, or missing evidence;
- silently overwrite an earlier analysis;
- choose a market or dispose of a veto.

All deterministic math runs in typed backend code and stores a calculation breakdown.

## 2. Pipeline

```text
eligible normalized document/version
  -> relevance extraction
  -> schema validation
  -> accepted/possible/irrelevant routing
  -> methodology-specific extraction
  -> schema and evidence-span validation
  -> proposed evidence records
  -> human review/sampling
  -> embeddings and deterministic clustering/aggregation
  -> optional AI cluster naming/summarization
  -> deterministic scoring input
```

`Possibly Relevant` content is queued for human review or an approved second-stage classifier. `Irrelevant` content does not receive expensive methodology extraction unless selected for evaluation.

## 3. Analysis version tuple

Every analysis run records:

```text
analysis_type
analysis_version
prompt_version
schema_version
taxonomy_version
model_reference
normalization_version/input hash
generation settings needed for reproducibility
created_at/status
token/cost metadata
validation errors
```

Changing prompt, model, taxonomy, normalization, schema, or material post-processing creates a new run/version. Historical output is never overwritten. Provider model names are references, not assumptions of eternal reproducibility; the exact input/output and versions support audit.

## 4. Prompt requirements

Every production prompt must:

- state the market definition and analysis task without asking for a market score;
- require JSON/structured output matching the registered schema;
- instruct the model to use only supplied source content;
- distinguish `unknown/not stated` from negative evidence;
- require exact evidence spans for material claims;
- preserve contradictory findings;
- use the canonical taxonomies and scales;
- avoid inferring sensitive personal attributes;
- resist instructions embedded in source text by treating evidence as untrusted data;
- specify multi-item behavior and empty-result behavior;
- be version-controlled and paired with evaluation fixtures.

Untrusted source text is delimited separately from system/task instructions. Tool use and network access are disabled for extraction unless an explicitly reviewed pipeline requires them.

## 5. Common field conventions

- Optional unknown values are `null`; never `0`, empty text, or invented defaults.
- Confidence is extraction confidence about a specific field/record, not market confidence.
- Evidence spans must be exact substrings or valid character offsets into the analysed normalized version.
- Numeric fields are range validated but remain proposed until reviewed.
- Taxonomy outputs use stable IDs plus optional human-readable labels.
- Each extracted record identifies source document and analysis run outside the model payload.

## 6. Structured extraction contracts

The following are logical contracts. Phase 1/feature implementation will encode them as versioned Pydantic/JSON Schemas.

### 6.1 Relevance classification v1

```json
{
  "label": "relevant | possibly_relevant | irrelevant",
  "reasons": ["short source-grounded reason"],
  "evidence_spans": ["exact excerpt"],
  "confidence": 0.0
}
```

Validation: confidence is 0–1; relevant/possible requires at least one valid span. A reason alone is not evidence.

### 6.2 Persona classification v1

```json
{
  "persona": "owner | executive | manager | employee | customer | vendor | unknown",
  "evidence_span": "exact excerpt or null",
  "confidence": 0.0
}
```

Do not infer role from stereotypes. `Unknown` is valid and preferred to unsupported certainty.

### 6.3 Commercial pain extraction v1

One document can yield zero or more records:

```json
{
  "pain_present": true,
  "pain_category": "taxonomy id or null",
  "pain_subcategory": "taxonomy id or null",
  "pain_description": "concise normalized description",
  "sentiment": -2,
  "severity_1_10": 1,
  "urgency_1_10": 1,
  "economic_impact_types": ["revenue_leakage"],
  "economic_impact_1_10": 1,
  "purchase_intent_0_4": 0,
  "existing_workaround": "text or null",
  "solution_dissatisfaction_1_10": 1,
  "ai_suitability_1_10": 1,
  "software_mentioned": ["name"],
  "financial_value_mentioned": [
    {"amount": 0, "currency": "USD", "period": "annual", "evidence_span": "exact excerpt"}
  ],
  "evidence_span": "exact excerpt",
  "confidence": 0.0
}
```

Rules:

- `pain_present=false` produces no scored pain fields.
- Sentiment -2..2 is distinct from severity.
- Numeric values must be grounded in language/context; missing fields are null rather than midpoints.
- Financial amounts are extracted only when explicitly present; estimates made by the model are forbidden.
- Persona is stored separately and attached during persistence.

### 6.4 General evidence extraction v1

```json
{
  "methodology_id": "M1",
  "evidence_type": "stable taxonomy id",
  "polarity": "supporting | contradictory | neutral",
  "claim": "source-grounded claim",
  "evidence_span": "exact excerpt",
  "strength": "weak | moderate | strong",
  "confidence": 0.0
}
```

`strength` is a proposed evidence characteristic, not a method score. It is eligible for aggregation only after review/rubric rules.

### 6.5 Competitor extraction v1

```json
{
  "competitor_name": "name",
  "competitor_type": "direct_ai_vendor | vertical_saas | agency | consultancy | bpo | internal_diy",
  "target_market": "text or null",
  "target_buyer": "text or null",
  "problem_solved": ["text"],
  "pricing": {
    "status": "exact | starting_at | estimated | unknown",
    "amount": null,
    "currency": null,
    "period": null,
    "evidence_span": null
  },
  "features": ["text"],
  "integrations": ["text"],
  "positioning": "text or null",
  "strengths": ["source-grounded text"],
  "weaknesses": ["source-grounded text"],
  "evidence_spans": ["exact excerpt"],
  "confidence": 0.0
}
```

`estimated` is permitted only when the source itself presents an estimate or an analyst-supplied, evidenced estimation rule is applied after extraction. The LLM does not estimate absent pricing.

### 6.6 Search-intent classification v1

```json
{
  "keyword": "normalized keyword",
  "intent_type": "problem | informational | solution | commercial | comparison | transactional | competitor_switching",
  "alternative_intent": "intent or null",
  "confidence": 0.0
}
```

Volume, CPC, competition, geography, and date come from source data, not the classifier.

### 6.7 Interview extraction v1

```json
{
  "findings": [
    {
      "finding_type": "pain_confirmed | pain_rejected | urgency | existing_spend | workflow_detail | buying_authority | buying_objection | current_solution | willingness_to_solve | contradiction",
      "claim": "participant-grounded finding",
      "evidence_span": "exact transcript excerpt",
      "confidence": 0.0
    }
  ],
  "unresolved_questions": ["text"]
}
```

Interview identity and consent metadata are supplied by the application, not inferred by the model. Summaries inherit the transcript's restricted access.

### 6.8 Cluster naming v1

Input contains representative, reviewed mention descriptions and cluster statistics produced outside the model. Output:

```json
{
  "name": "short neutral cluster name",
  "description": "grounded scope description",
  "out_of_scope_signals": ["possible mismatch"],
  "confidence": 0.0
}
```

The LLM does not choose membership, recompute statistics, or omit dissenting/outlier records.

## 7. Embeddings and clustering

- Embed normalized pain descriptions, not arbitrary keyword bags.
- Store embedding model/version/dimensions with every vector.
- Deduplicate before clustering to prevent repeated text from dominating.
- Use versioned deterministic preprocessing, distance metric, algorithm, parameters, random seed, and outlier policy.
- Store every cluster membership and similarity/probability.
- AI may name a completed cluster from representative members; humans approve material cluster names and merges/splits.
- A new model or parameter set creates a new clustering run, never an in-place rewrite.

## 8. Validation and failure handling

1. Parse against the exact schema.
2. Enforce types, ranges, enums, required/null rules, and maximum lengths.
3. Verify evidence spans/offsets against the analysed text.
4. Apply deterministic consistency checks (for example no amount without a supporting span).
5. Reject or quarantine invalid output; do not coerce materially ambiguous fields.
6. A bounded repair retry may receive only validation errors and original input under the same prompt/model version; record it as an attempt.
7. Persistent failure creates a failed analysis run and a reviewable job error.

No unvalidated model output reaches scoring inputs.

## 9. Human review

AI records begin `proposed`. A reviewer can accept, correct, reject, or supersede. Corrections retain the original output and create the reviewed value/event. High-impact fields—financial values, buying intent 3–4, severe pain, competitor pricing, workflow economics, and interview contradictions—receive risk-based review priority.

Sampling rates can fall after demonstrated quality but never below the method's approved evaluation/control policy. New prompt, model, schema, or taxonomy versions return to enhanced sampling until release gates pass.

## 10. AI security, privacy, and cost controls

All AI-enabled execution also follows the hard-stop rules in [COST_CONTROL.md](COST_CONTROL.md). Paid calls default to disabled; a configured run must have finite currency, request, token, document/excerpt, retry, and duration limits. Deterministic filtering, exact deduplication, bounded excerpts, and version-aware result reuse happen before a model call. Reaching a budget produces an honest partial/needs-review result, never silent overspend or false completeness.

- Send only the minimum text and metadata required.
- Use approved providers/configurations for restricted interviews or commercial data; prohibit provider training/retention where required by policy.
- Redact unnecessary direct identifiers before inference.
- Treat source content as untrusted prompt-injection material.
- Do not expose secrets, credentials, private URLs, or cross-tenant data in prompts/logs.
- Enforce per-job/document size and token limits, concurrency budgets, and cost attribution.
- Store private raw model payloads only where needed for audit/evaluation and under inherited retention rules.

## 11. Release requirement

No extraction version is eligible for production scoring inputs until it passes the relevant evaluation suite in `EVALUATION.md`, has an approved schema/taxonomy/prompt version, and supports lineage to valid evidence spans.
