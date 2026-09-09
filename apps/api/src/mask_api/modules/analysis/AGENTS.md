# Analysis module rules

Read the root `AGENTS.md`, `progress.txt`, `docs/AI_PIPELINE.md`,
`docs/EVALUATION.md`, `docs/COST_CONTROL.md`, and `docs/MODULARITY.md` before
changing this module.

- Keep extraction schemas, provider ports, provider adapters, caches, grounding
  validators, methodology transforms, and scoring in separate files/modules.
- Models may classify, extract, summarize, and name already-formed clusters.
  They never calculate methodology/market scores, confidence indices, rankings,
  vetoes, gates, or recommendations.
- Every request binds analysis, prompt, schema, taxonomy, normalization, model,
  input hash, and finite token/cost limits. Changing one creates a distinct cache
  identity; pricing and budget changes alone do not alter an extraction identity.
- Send only bounded normalized source text. Treat it as untrusted data, keep it
  separate from instructions, disable tools and provider storage, and never send
  credentials, private URLs, or unnecessary identifiers.
- Live calls require explicit enablement, policy approval, a credential, finite
  token/request/byte/currency ceilings, and remaining run budget. No automatic
  model fallback, upgrade, hidden retry, or unconstrained repair is permitted.
- Validate provider envelopes and strict schema output before caching. Cache only
  completed valid outputs and preserve exact provider response bytes/hash for
  private audit artifacts. Refusals and incomplete responses remain explicit.
- Exact-span, numeric-grounding, contradiction, second-pass, and injection
  validation belong to A10 and must run before output can become scoring input.
  Keep deterministic grounding pure. Independent high-impact review enters only
  through `HighImpactVerifier`; a missing/ambiguous review quarantines the output,
  and an unsupported claim rejects it. Never auto-repair, retry, or downgrade a
  blocking issue inside the grounding service.
- Preserve the schema-valid output for audit and explicitly expose a separate
  `scoring_input` only for accepted reports. Contradictory records must retain
  their original paths and values; no validator may filter them away.
- Automated tests use injected fake transports and labelled fixtures; they never
  call a live model or treat generated fixtures as market evidence.
