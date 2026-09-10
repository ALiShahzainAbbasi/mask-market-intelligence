# Structured Analysis Provider Boundary

Status: A09 offline implementation; A17.5 adds a second, still offline-tested
provider (Gemini). Live model execution remains held for both.

`mask_api.modules.analysis` implements the provider-neutral boundary described in
`AI_PIPELINE.md`. It contains immutable request/result/version/usage contracts,
the nine v1 extraction schemas, a typed provider/cache interface, an immutable
local artifact cache, and OpenAI Responses and Gemini `generateContent`
mapping/parser pairs. It contains no method score, market score,
confidence-index, gate, ranking, or recommendation.

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

## Gemini mapping (A17.5)

`mask_api.modules.analysis.gemini` mirrors the OpenAI adapter's exact shape
(`GeminiSettings`/`GeminiTransportResponse`/`GeminiTransport` Protocol/
`build_generate_content_payload`/`parse_generate_content_result`/
`GeminiAdapter`) against the same `AnalysisProvider` port, `AnalysisRequest`/
`AnalysisResult` contracts, and `ArtifactAnalysisCache`. It calls Gemini's
`generateContent` REST endpoint directly (no Google SDK dependency), reads
its credential from `MASK_gemini_API_KEY` (the owner-supplied name, reused
as-is), and stays disabled until both `enabled` and `policy_approved` are
set. The untrusted source text is carried only inside a JSON data object in
the user turn; the extraction-boundary system instruction is fixed and
never derived from source content, so embedded "ignore previous
instructions"-style text in a document cannot change adapter behavior --
only what the extraction records as a claim, which grounding validation
(`GROUNDING_VALIDATION.md`) still checks against the source span.

Gemini's `responseSchema` dialect is a restricted OpenAPI-3.0-like subset:
it does not accept `$ref`/`$defs` or `additionalProperties`.
`to_gemini_schema` inlines every `$ref` against the schema's own `$defs`
and drops the unsupported keys before the request is sent; this narrows
only the "reject unlisted extra properties" guarantee OpenAI's strict mode
adds, not required-field or type/enum validation, which Pydantic still
enforces when the structured output is parsed back. Gemini's response
envelope (`candidates`/`usageMetadata`/`promptFeedback`/`finishReason`) is
mapped to the identical COMPLETED/REFUSED/INCOMPLETE states the OpenAI
adapter uses, so both providers are interchangeable to every caller of the
`AnalysisProvider` port. As with OpenAI, no concrete transport is bundled,
the adapter cannot call a model under the current configuration, and
Gemini may only extract/classify/summarize -- it never calculates a score,
confidence index, gate, veto, or ranking.

A10 now supplies the separate mandatory grounding gate described in
`GROUNDING_VALIDATION.md`. Output from either provider alone is never
scoring input.
