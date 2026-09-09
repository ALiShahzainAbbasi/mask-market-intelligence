# Structured Analysis Grounding Gate

Status: A10 offline implementation.

`mask_api.modules.analysis.grounding` is the mandatory boundary between a valid
provider response and future deterministic methodology transforms. It performs
no model call, repair, calculation, ranking, or scoring.

## Deterministic checks

The gate revalidates the registered A09 schema and request identity. It then:

- requires material evidence spans to be exact, case-sensitive substrings of the
  normalized source version;
- checks numbers in material claims against their linked spans and normalizes
  comma notation plus `k`, `m`, and `b` suffixes for equality;
- requires known personas and non-unknown competitor pricing to carry evidence;
- detects bounded instruction-override, role-spoofing, secret-exfiltration, and
  tool-activation signals in untrusted source text;
- records contradictory general-evidence and interview paths without removing or
  rewriting those records; and
- emits stable high-impact claim IDs for financial values, purchase intent 3–4,
  severe pain 8–10, non-unknown competitor pricing, numeric M3 workflow economics,
  and interview contradictions.

The severe-pain threshold is a conservative review-priority rule, not a method
score or methodology weight. Changing it requires a new grounding version.

## Independent second pass

`HighImpactVerifier` is a narrow injected port. The default service has no
verifier and makes no external request. A future human or explicitly approved,
budgeted provider can return `supported`, `ambiguous`, or `unsupported` for the
stable claim IDs. The service never retries or falls back automatically.

- Missing or ambiguous verification produces `needs_review`.
- Unsupported verification or a deterministic grounding failure produces
  `rejected`.
- Prompt-injection signals produce `needs_review` and prevent automatic verifier
  dispatch.
- Only an `accepted` report exposes `scoring_input`; all other output remains
  quarantined while `preserved_output` remains available for audit/review.

This gate establishes engineering behavior, not AI release approval. Production
extraction still needs the labelled datasets and thresholds in `EVALUATION.md`.
