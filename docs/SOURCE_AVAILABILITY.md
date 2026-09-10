# Source Availability and Hold Policy

Status: owner-approved lean operating policy as of 2026-09-10 (source profile v2).

## Decision

An unavailable account API must not block implementation of the research system.
The default source profile records operational availability independently from
policy status, credential requirements, and cost class. This keeps the system
honest about why a source cannot run and prevents an unavailable or paid source
from being activated accidentally.

| Operational status | Meaning | Default behavior |
| --- | --- | --- |
| `available` | Usable without a missing account dependency | Still opt-in and policy-gated |
| `credential_pending` | Free or mixed API exists, but this installation lacks its credential | Stop before network access |
| `approval_pending` | Provider/account approval is required | Stop before network access |
| `paid_hold` | Source requires paid access under the current profile | Stop before network access and spend |

The current approved source set is below. “Approved” means available to the
implementation; every actual run is still opt-in, policy-gated, bounded, and
recorded. Credential values live only in ignored local environment files.

| Source | Type | Research use | Current state |
| --- | --- | --- | --- |
| Census County Business Patterns | Official API | M1 establishments, employment bands, payroll, and geography | Available; local key configured; one-query live smoke passed |
| BEA Regional | Official API | M1/M4 regional income, employment, GDP, and economic-capacity context | Available; local key configured; one-query live smoke passed |
| SAM.gov opportunities | Official API | M3/M4/M5/M6 procurement demand, requirements, incumbents, and pricing clues | Available; local key configured; one-query live smoke passed |
| SEC EDGAR | Official keyless API | M1/M4/M5 named-company filings, competition, spend, risks, and pricing evidence | Available; contact user-agent required; one-query live smoke passed |
| BLS Public Data API | Official keyless API | M1/M4 employment, wage, industry-growth, and labor-cost series | Available with limited unregistered quotas; one-series live smoke passed |
| USAspending award search | Official keyless API | M4/M5 awarded federal contract spend, incumbents, and economic-demand evidence | Available; keyless; added under A17.5; offline-tested only, live smoke not yet run |
| YouTube Data API v3 | Official keyed API | M2/M3/M5 public pain, workflow, and competitor-discussion evidence from video search and comment threads | Available; local key configured under A17.5; adapter offline-tested against a fake transport only, no live smoke run yet |
| Registered RSS/Atom feeds | Permitted feed retrieval, not an account API | M2-M7/M9 approved public article and discussion evidence | Available only for explicitly registered feeds and current source policy |
| Registered static webpages | Permitted page retrieval, not an account API | M2-M7/M9 approved public source evidence | Available only for exact registered pages; never broadened into crawling |
| Analyst-supplied evidence | Manual/import input, not an API | Reviewed documents, observations, and market-specific context with provenance | Approved source category; bounded upload/manual-capture implementation remains P03-04 |

Google Ads Keyword Planner, Reddit, and Meta remain credential- or
provider-approval pending and are intentionally skipped. Google Places, Brave
Search, licensed firmographics, and validation accounts remain on paid hold. A
later owner decision may create a new source-profile version and budget; code
must never silently flip these states.

## Research behavior during a hold

- Attempt only sources marked `available`, explicitly enabled, and approved by a
  current source policy.
- Record the unavailable source and reason in run lineage.
- Use an approved free fallback only when it supports the same named signal.
- Leave the value or method `UNKNOWN` when the missing source is required; never
  convert unavailability to zero or fabricate a proxy metric.
- Do not treat repeated content from one source family as independent source
  diversity.
- Do not broaden a registered static-HTML or feed collector into a crawler.

## Resuming a held source

To resume, record the credential/account approval, current terms/policy review,
allowed purpose and fields, retention, source limits, and any positive paid
budget. Change `operational_status` in an approved source-profile version, run
its deliberately small live smoke, and retain the profile hash with the run.
