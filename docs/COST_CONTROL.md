# Lean research and cost-control contract

Status: mandatory for the private Windows MVP under ADR 0003.

The goal is enough defensible evidence to compare markets—not maximum collection, maximum automation, or maximum model usage. Cost controls are execution safety rules; they do not alter methodology weights or let a thin evidence set masquerade as high confidence.

## Default operating profile

- Start with the guide's 3–5-market technical pilot; use 3 unless a documented evidence need justifies more.
- Start with 2 permitted collectors and add at most the third initial collector only when it fills a named evidence gap.
- Prefer analyst uploads, official APIs, permitted exports, and simple HTTP collection before browser automation.
- Collect and analyze incrementally. Stop when the current gate has enough reviewed evidence; do not gather data merely because more is available.
- Keep one background worker with concurrency 1. Higher concurrency is an explicit operator choice bounded by source limits and spend limits.
- Delay every feature listed in the guide's deferred section until the underlying workflow proves useful.

## Paid-model controls

Paid model calls are disabled by default. Enabling them requires an approved provider configuration and all of these finite per-run limits:

- maximum provider cost in the owner's chosen currency;
- maximum requests;
- maximum input and output tokens;
- maximum documents and excerpts;
- maximum repair/retry attempts; and
- maximum wall-clock duration.

The job stops before the next call would exceed a limit. It records the limit reached, actual usage, partial outputs, model reference, prompt/schema version, and input hash. No automatic fallback may silently select a more expensive model or exceed the configured budget.

## Cheapest-valid processing order

1. Apply source policy and access checks.
2. Normalize and exact-deduplicate with deterministic code.
3. Apply cheap deterministic filters and metadata rules.
4. Use a small/low-cost relevance classifier only for unresolved items when configured.
5. Send only relevant, bounded excerpts to structured extraction.
6. Cache by normalized input hash plus prompt/model/schema version; never repay for an identical valid result.
7. Embed only unique retained evidence needed for retrieval/deduplication/clustering.
8. Cluster with deterministic code; an LLM may name a completed cluster only when useful.
9. Calculate scores, confidence, ranking, and gates only in deterministic backend code.
10. Ask a human to review ambiguous, high-impact, or low-confidence results instead of escalating model cost automatically.

Batching is allowed only when source lineage and per-item validation remain intact. A bounded repair call receives validation errors and the original input; repeated unconstrained retries are forbidden.

## Research sufficiency and honesty

- Source/document caps are configured before a run and stored with it. Initial numeric caps are operational settings, not hidden methodology thresholds.
- Reaching a cost or volume cap produces `partial` or `needs_review`, never false completeness.
- Low sample size, weak source diversity, stale evidence, and unfilled method requirements reduce completeness/confidence according to approved deterministic rules.
- Manual evidence and manual method scoring remain first-class and traceable. Manual does not mean unreviewed or unaudited.
- Real collection, outreach, paid experiments, and private-data processing still require their existing approvals.

## Features deliberately outside the lean MVP

Do not add broad social scraping, every market-data API, autonomous workflow mapping, predictive success ML, automated outreach/interviews, complicated multi-agent systems, a data warehouse, Kubernetes, or cloud services solely for scale. Revisit only after the 3–5-market pilot shows a measured bottleneck.

