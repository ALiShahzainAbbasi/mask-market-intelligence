# Structured Analysis Provider Boundary

Status: A09 offline implementation; live model execution remains held.

`mask_api.modules.analysis` implements the provider-neutral boundary described in
`AI_PIPELINE.md`. It contains immutable request/result/version/usage contracts,
the eight v1 extraction schemas, a typed provider/cache interface, an immutable
local artifact cache, and an OpenAI Responses mapping/parser. It contains no
method score, market score, confidence-index, gate, ranking, or recommendation.

## Request identity and cost controls

Every request binds the analysis type, schema, analysis/prompt/schema/taxonomy/
normalization versions, normalized document hash, market definition, task,
bounded source text, caller-selected model reference, and output-token limit.
The cache identity deliberately excludes pricing and budget values, because a
price change does not change the meaning of an otherwise identical extraction.

The caller supplies the model reference and its current input/output prices;
the adapter never selects or upgrades a model. Before network transport it
reserves one request, the maximum response bytes, and the worst-case configured
call cost against the shared run budget. The response's usage must remain within
the input/output token ceilings and call-cost cap before the actual cost is
recorded. No retry or fallback is implemented.

## Provider mapping

The OpenAI mapping uses the Responses API with `store: false`, no tools, bounded
output tokens, and `text.format.type: json_schema` with strict JSON Schema. The
source is encoded as a distinct untrusted-data object, while stable extraction
rules remain in provider instructions. Provider envelopes can produce completed,
refused, or incomplete results; only completed schema-valid outputs are cached.

No concrete credential-bearing network transport or OpenAI SDK is installed.
The adapter is disabled by default and cannot call a model under the current
configuration. Tests use injected fake bytes only. Current OpenAI documentation
requires closed objects and all object fields to be required for strict output;
the generated schemas do both. Standard supported models can use the emitted
type-specific constraints. A future fine-tuned model profile must first prove
compatibility because its supported JSON Schema subset can be narrower.

A10 now supplies the separate mandatory grounding gate described in
`GROUNDING_VALIDATION.md`. A09 output alone is never scoring input.
