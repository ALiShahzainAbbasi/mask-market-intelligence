# M2 Pain Intelligence

Status: A11 offline implementation.

`mask_api.modules.pain_intelligence` implements the zero-paid-cost M2 processing
path after A10 grounding. It does not collect sources or invoke an LLM. It accepts
only `GroundingReport` values that are accepted and explicitly expose
`scoring_input`.

## Pipeline

```text
A10-accepted commercial-pain-v1 output
  -> lineage-rich pain mentions
  -> exact normalized-text dedupe within persona
  -> versioned embedding cache/provider
  -> near dedupe within persona
  -> deterministic complete-linkage cosine clusters within persona
  -> cluster components from formulas/v1.yaml
  -> max + sqrt(document)-weighted top-five M2 aggregation
  -> lineage-rich report contract
```

Exact mention duplicates require the same normalized-document hash and normalized
pain text; high-threshold near duplicates use versioned embedding similarity. The
service never merges different personas. Duplicate records retain links but
cannot increase frequency, means, source-family counts, sample adequacy, or
cluster weights. Every cluster retains all membership IDs, membership similarity,
outlier state, representative mention IDs, component sample counts, and linked
contradictions.

## Lean embedding path

The default offline adapter is `local_hashing / mask-lexical-hashing / v1`. It is
a deterministic signed word-and-bigram feature hash, uses no network or model,
has no paid cost, and downloads no dependency. It makes the Windows MVP runnable
and reproducible, but it is not presented as production semantic-model quality.

`EmbeddingProvider` and `EmbeddingCache` keep a later semantic provider
replaceable. Cache identity binds provider, model reference, embedding version,
dimensions, and normalized input hash. Provider responses must match every input
and all lineage exactly; no fallback or auto-upgrade exists.

## Formula and honest status

The calculator consumes the validated M2 `MethodFormula` loaded from
`configs/formulas/v1.yaml`; it does not ask a model to score. Per cluster it uses:

- frequency: unique cluster documents / all relevant unique documents, mapped
  linearly from 0.02–0.20 to 0–10;
- mean available verified severity and economic impact on 0–10;
- mean purchase intent on 0–4, multiplied by 2.5; and
- mean solution dissatisfaction on 0–10.

Any unavailable component in a non-outlier cluster makes M2 `unknown`. Fewer
than 100 relevant unique documents is also `unknown`. A known score is
`provisional` below 500 relevant unique documents or three retained independent
source families. Otherwise it is `complete`. The market score is 50% of the
maximum eligible cluster score plus 50% of the square-root-document-weighted mean
of the top five, exactly as configured.

These statuses are calculation completeness, not AI-quality approval. A later
semantic embedding choice, cluster review, persistence, the 100–200 labelled AI
evaluation set, and production scoring release remain governed by `EVALUATION.md`
and Phase 4. Local fixtures never count as market evidence.
