# Canonical Data Model

Status: Phase 0 logical model; Phase 1 infrastructure migration and Phase 2 identity/market schema are implemented in files. Live migration/constraint verification remains outstanding.

## 1. Conventions

- Primary keys are UUIDs unless an approved migration documents another choice.
- Tenant-owned records carry `organization_id`; child tables may inherit tenant scope through a required parent, but repository queries must still enforce it.
- Mutable business records carry `created_at`, `updated_at`, and an optimistic `version` where concurrent review matters.
- Controlled vocabularies use database enums only when migration cost is acceptable; otherwise use validated code tables.
- JSON is reserved for source-specific or versioned payloads that do not replace queryable canonical fields.
- Monetary values store amount, ISO currency, period/basis, and provenance. Percentages store explicit scale.
- Dates distinguish source publication, observation period, collection, extraction, review, and decision time.
- AI-derived records always point to an `analysis_run`.
- Scores and decisions are immutable snapshots/events; corrections create successors.
- Raw evidence is append-only in normal operation. A controlled legal/privacy deletion workflow may tombstone or purge required content while preserving a non-sensitive audit record.

## 2. Relationship overview

```text
organization -> users -> credentials / server_sessions
identity actions -> identity_security_events
organization -> markets -> market_definition_versions -> hypotheses
market -> collector_runs -> raw_documents -> normalized_document_versions
raw_document -> analysis_runs -> evidence_items / pain_mentions / extracted findings
pain_mentions -> pain_cluster_memberships -> pain_clusters
market -> methodology records -> method_scores -> method_score_evidence
market -> market_score_snapshots -> stage_gate_decisions
market -> red_flags
all material mutations -> audit_events
```

## 3. Identity and tenancy

### `organizations`

`id`, `name`, `status`, `created_at`, `updated_at`.

### `users`

`id`, `organization_id`, `name`, `email`, `status`, `created_at`, `updated_at`.

Email is unique within an organization and normalized for comparison.

### `user_roles`

`id`, `organization_id`, `user_id`, `role`, `created_at`.

Allowed roles: `researcher`, `reviewer`, `sales`, `technical`, `founder`, `admin`. A user can hold multiple roles.

### `user_credentials`

One local credential per user: `organization_id`, `user_id`, maintained Argon2id `password_hash`, `password_changed_at`, bounded failed-login count, `locked_until`, last failed/successful login times, and timestamps. No plaintext/recoverable password or reset secret is stored.

### `server_sessions`

Hashed server session: `id`, `organization_id`, `user_id`, unique SHA-256 `token_hash`, SHA-256 `csrf_hash`, authentication/creation/expiry/revocation times, revocation reason, and optional unique `rotated_from_id`. Raw session and CSRF values exist only at the browser boundary. Rotation creates a successor and revokes the source without extending absolute expiry.

### `identity_security_events`

Append-only authentication event: `id`, event type/outcome, optional trusted organization/user/session references, `correlation_id`, safe `reason_code`, and occurrence time. It records owner bootstrap, login success/failure/throttling, rotation, and revocation without email, password, cookie, raw token, or request payload.

## 4. Market registry

### `markets`

`id`, `organization_id`, `name`, `submarket`, `geography`, `company_size_definition`, `likely_buyer`, `description`, `stage`, `status`, `research_owner_id`, `reviewer_id`, `current_definition_version_id`, `created_at`, `updated_at`, `version`.

Stages: `broad_screen`, `deep_research`, `live_validation`, `finalist`, `selected`, `rejected`. Statuses include `active`, `hold`, `archived`; selected/rejected stage transitions remain decision-controlled.

### `market_definition_versions`

Immutable market comparison boundary: `id`, `market_id`, `version_number`, all market-defining fields, `change_reason`, `created_by`, `created_at`.

Changing geography, company band, likely buyer, or other material boundary creates a new version so earlier evidence/scores remain interpretable.

### `market_hypotheses`

`id`, `market_id`, `market_definition_version_id`, `hypothesis_type`, `statement`, `status`, `created_by`, `created_at`, `updated_at`.

Statuses: `proposed`, `supported`, `contradicted`, `inconclusive`, `retired`.

### `research_plans`

`id`, `market_id`, `market_definition_version_id`, `research_profile`, `methodology_version`, `status`, `required_evidence_json`, `created_by`, `created_at`, `approved_by`, `approved_at`.

### Phase 2 physical implementation notes (Alembic 0002 and 0004)

The identity and market modules implement the tables in sections 3-4. The physical layout is defined in feature-owned models and frozen migrations. Alembic 0004 adds local authentication persistence, but the tested auth HTTP adapter remains unregistered and no market workflow is enabled yet.

- All non-organization tables explicitly carry organization_id. Composite foreign keys ensure owners, reviewers, authors, approvers, and assigned roles refer to same-tenant users.
- Definitions are unique by organization/market/version_number. Hypotheses and research plans reference organization + market + definition together, preventing same-tenant cross-market substitutions as well as cross-tenant links.
- A market requires a current definition. Its composite pointer is DEFERRABLE INITIALLY DEFERRED so the market and initial snapshot can be inserted in one transaction. The service must prepare both UUIDs and persist both records before commit.
- The application role receives SELECT/INSERT, not UPDATE/DELETE, on definition snapshots. Privileged migration identities remain separate. No application DELETE privileges are granted by 0002.
- User emails must be lowercased/trimmed and unique per organization at the database boundary. Alembic 0004 keeps credentials separate from users and stores only Argon2id password hashes plus hashed random session/CSRF identifiers. An email address or submitted organization ID alone never grants access.
- Credential and session foreign keys include organization and user. Session token hashes and rotation sources are unique; database checks enforce fixed lowercase hexadecimal digests, ordered timelines, and paired revocation time/reason. Security events are application-append-only.
- Organization status is active/suspended; user status is invited/active/suspended. Research plans use draft/approved/retired. These are operational lifecycle choices, not research scoring rules. Invited users are not automatically authenticated.
- New markets default to broad_screen/active, with a required owner and optional reviewer. The organization-specific separation-of-review policy and stage-change permission checks remain application work.
- Mutable timestamp mixins provide ORM updated_at behavior; bulk SQL must explicitly update timestamps. Market.version is the ORM optimistic-concurrency column. P02-03 must add compare-and-swap handling for all mutation paths.
- Research-plan JSON must be an object. Approval actor/time must be paired; approved plans require them, and draft plans cannot contain approval metadata. Evidence adequacy and acting-role authorization are separate unfinished use-case rules.
- UUIDs are allocated by the application; there is no silent account, market, plan, or research seeding.

These constraints protect referential integrity, not tenant-scoped SELECT permissions. Authentication, authorization, query filters, audit behavior, and actual PostgreSQL enforcement must all pass their own tests before product use.

## 5. Source governance and collection

### `sources`

`id`, `organization_id` nullable for global catalog entries, `name`, `source_type`, `base_url`, `collection_method`, `status`, `policy_notes`, `robots_reviewed_at`, `terms_reviewed_at`, `authentication_requirements`, `default_rate_limit_json`, `retention_class`, `created_at`, `updated_at`.

Collection methods: `official_api`, `permitted_http`, `permitted_browser`, `third_party`, `analyst_upload`, `manual_capture`. Status includes `allowed`, `conditional`, `blocked`, `review_required`.

### `source_policy_versions`

`id`, `source_id`, `version_number`, `status`, `allowed_actions_json`, `rate_limit_json`, `authentication_requirements`, `retention_rule`, `policy_notes`, `approved_by`, `effective_at`, `retired_at`, `created_at`.

### `collector_runs`

`id`, `organization_id`, `market_id`, `market_definition_version_id`, `source_id`, `source_policy_version_id`, `collector_type`, `collector_version`, `query`, `idempotency_key`, `started_at`, `completed_at`, `status`, `documents_found`, `documents_saved`, `documents_duplicate`, `documents_rejected`, `error_code`, `error_message`, `created_by`.

### `jobs`

Generic asynchronous job record: `id`, `organization_id`, `market_id` nullable, `job_type`, `status`, `progress_current`, `progress_total`, `idempotency_key`, `input_reference_json`, `configuration_versions_json`, `attempt_count`, `max_attempts`, `queued_at`, `started_at`, `completed_at`, `error_code`, `error_message`, `output_reference_json`, `correlation_id`.

### `uploaded_files`

`id`, `organization_id`, `market_id`, `storage_reference`, `original_filename`, `media_type`, `size_bytes`, `checksum`, `access_class`, `uploader_id`, `uploaded_at`, `scan_status`, `parser_version`, `retention_until`.

The storage reference never embeds a public credential.

### `raw_documents`

`id`, `organization_id`, `market_id`, `market_definition_version_id`, `source_id`, `collector_run_id` nullable, `uploaded_file_id` nullable, `source_url`, `external_id`, `title`, `author_type`, `published_at`, `collected_at`, `raw_text` or controlled object reference, `language`, `content_checksum`, `metadata_json`, `access_class`, `retention_class`, `created_at`.

Raw documents are not overwritten when parsing or AI logic changes. `source_url + external_id` and checksums support idempotency, but multiple provenance records may point to the same content.

### `normalized_document_versions`

`id`, `document_id`, `normalization_version`, `normalized_text`, `content_hash`, `language`, `created_at`, `is_current`.

### `document_duplicate_links`

`id`, `document_id`, `canonical_document_id`, `duplicate_type` (`exact`, `near`), `similarity` nullable, `algorithm_version`, `review_status`, `reviewed_by`, `created_at`.

### `document_embeddings`

`id`, `document_id`, `normalized_document_version_id`, `provider`, `model_reference`, `dimensions`, `embedding`, `created_at`.

One embedding is unique per normalized version/model/dimensions.

## 6. AI analysis and general evidence

### `analysis_runs`

`id`, `organization_id`, `document_id` nullable, `interview_id` nullable, `analysis_type`, `analysis_version`, `prompt_version`, `schema_version`, `taxonomy_version`, `model_reference`, `input_hash`, `status`, `raw_output_reference` nullable, `validation_errors_json`, `token_usage_json`, `cost_metadata_json`, `created_at`, `completed_at`.

### `evidence_items`

`id`, `organization_id`, `market_id`, `document_id` nullable, `interview_id` nullable, `analysis_run_id` nullable, `methodology_id`, `evidence_type`, `polarity`, `claim`, `supporting_text`, `source_start` nullable, `source_end` nullable, `strength`, `extraction_confidence`, `review_status`, `reviewed_by`, `reviewed_at`, `created_at`, `supersedes_id` nullable.

Polarity: `supporting`, `contradictory`, `neutral`. Review status: `proposed`, `accepted`, `corrected`, `rejected`, `superseded`.

### `evidence_links`

Links evidence to hypotheses, findings, metrics, workflow steps, competitors, experiments, or red flags: `id`, `evidence_item_id`, `target_type`, `target_id`, `relationship`, `created_at`.

## 7. Pain intelligence (M2)

### `pain_mentions`

`id`, `organization_id`, `market_id`, `document_id`, `analysis_run_id`, `persona`, `pain_present`, `pain_category`, `pain_subcategory`, `pain_description`, `sentiment`, `severity`, `urgency`, `economic_impact_types_json`, `economic_impact`, `purchase_intent`, `existing_workaround`, `solution_dissatisfaction`, `ai_suitability`, `software_mentioned_json`, `financial_value_mentioned_json`, `evidence_span`, `extraction_confidence`, `review_status`, `reviewed_by`, `created_at`, `supersedes_id`.

### `pain_mention_embeddings`

`id`, `pain_mention_id`, `provider`, `model_reference`, `dimensions`, `embedding`, `created_at`.

### `pain_clusters`

`id`, `organization_id`, `market_id`, `cluster_run_id`, `name`, `description`, `mention_count`, `frequency`, `average_severity`, `average_urgency`, `average_economic_impact`, `average_purchase_intent`, `average_dissatisfaction`, `opportunity_score`, `calculation_json`, `review_status`, `reviewed_by`, `created_at`.

### `pain_cluster_memberships`

`id`, `pain_cluster_id`, `pain_mention_id`, `membership_score`, `is_outlier`, `created_at`. Membership lineage is mandatory.

### `clustering_runs`

`id`, `organization_id`, `market_id`, `algorithm`, `algorithm_version`, `parameters_json`, `embedding_model_reference`, `input_hash`, `status`, `created_at`, `completed_at`.

## 8. Method-specific evidence

### `quantitative_metrics` (M1)

`id`, `market_id`, `metric_type`, `value`, `unit`, `currency` nullable, `period_start`, `period_end`, `geography`, `population_definition`, `provenance_type`, `source_id`, `document_id` nullable, `assumptions_json`, `review_status`, `created_at`.

### `workflow_maps` and `workflow_steps` (M3)

Map: `id`, `market_id`, `name`, `version_number`, `status`, `created_by`, `approved_by`, timestamps.  
Step: `id`, `workflow_map_id`, `sequence`, `name`, `role`, `system`, `input`, `output`, `frequency`, `handling_time`, `manual_work`, `waiting_time`, `failure_rate`, `business_consequence`, `current_workaround`, `automation_potential`, `estimated_value`, `value_provenance`, `evidence_confidence`, timestamps.

### `economic_evidence` (M4)

`id`, `market_id`, `evidence_category`, `amount`, `currency`, `period`, `provenance_type`, `range_low`, `range_high`, `assumptions_json`, `source_id`, `document_id` nullable, `interview_id` nullable, `review_status`, `created_at`.

### `roi_scenarios` (M4)

`id`, `market_id`, `name`, `current_annual_cost`, `estimated_revenue_leakage`, `current_solution_spend`, `recoverable_percentage`, `proposed_solution_cost`, input provenance references, `potential_economic_value`, `value_to_price_ratio`, `estimated_payback_months`, `annual_net_benefit`, `calculation_version`, `calculation_json`, `review_status`, timestamps.

### `competitors` and `competitor_findings` (M5)

Competitor: `id`, `organization_id`, `name`, `url`, `competitor_type`, timestamps.  
Finding: `id`, `market_id`, `competitor_id`, `target_market`, `target_buyer`, `problem_solved`, `pricing_amount` nullable, `pricing_currency` nullable, `pricing_status`, `features_json`, `integrations_json`, `positioning`, `case_studies_json`, `review_summary`, `customer_complaints`, `strengths`, `weaknesses`, `evidence_item_id`, `review_status`, timestamps.

Competitor type and pricing status use the taxonomies in `RESEARCH_METHODOLOGY.md`.

### `search_keywords` (M6)

`id`, `market_id`, `keyword`, `intent_type`, `search_volume`, `trend`, `cpc_amount`, `currency`, `competition`, `source_id`, `country`, `observation_date`, `evidence_item_id` nullable, `review_status`, timestamps.

### `buyer_personas` and `buyer_channels` (M7)

Persona: `id`, `market_id`, `stakeholder_type`, `title_patterns_json`, `authority_notes`, `evidence_item_id`, `review_status`, timestamps.  
Channel: `id`, `market_id`, `channel_type`, `target_accounts`, `identifiable_buyers`, `contact_data_availability`, `estimated_sales_cycle_days`, `procurement_complexity`, `channel_diversity`, `meta_suitability`, `metrics_json`, `evidence_item_id`, `review_status`, timestamps.

### `interviews` and `interview_findings` (M8)

Interview: `id`, `organization_id`, `market_id`, `participant_role`, `participant_fit`, `occurred_at`, `interviewer_id`, `consent_status`, `access_class`, `transcript_file_id` nullable, `notes`, `status`, timestamps.  
Finding: `id`, `interview_id`, `analysis_run_id` nullable, `finding_type`, `claim`, `evidence_span`, `strength`, `review_status`, `reviewed_by`, timestamps.

Participant direct identifiers should be stored separately or minimized; reporting uses pseudonymous identifiers.

### `product_fit_assessments` (M9)

`id`, `market_id`, `assessment_profile` (`light`, `full`), `technical_fit`, `integration_fit`, `delivery_complexity`, `standardization`, `recurring_revenue`, `proof_potential`, `expansion_potential`, `written_rationale`, `evidence_json`, `technical_reviewer_id`, `business_reviewer_id`, `status`, timestamps.

### `validation_experiments` (M10)

`id`, `market_id`, `channel`, `offer`, `message`, `start_date`, `end_date`, `spend`, `currency`, `audience`, `impressions`, `clicks`, `leads`, `qualified_leads`, `meetings`, `opportunities`, `proposals`, `sales`, `revenue`, `gross_profit`, `attribution_notes`, `data_quality`, `status`, timestamps.

### `validation_metrics` (M10)

`id`, `experiment_id`, `calculation_version`, `ctr`, `cpl`, `cost_per_qualified_lead`, `cost_per_meeting`, `opportunity_rate`, `close_rate`, `cac`, `revenue_cac`, `gross_profit_cac`, `sales_cycle_days`, `calculation_json`, `created_at`.

Metrics are derived, immutable calculation records rather than manually editable facts.

## 9. Scoring, confidence, gaps, and decisions

### `scoring_configurations`

`id`, `organization_id` nullable, `name`, `version`, `status`, `overall_weights_json`, `method_rubric_versions_json`, `confidence_version`, `gate_version`, `effective_at`, `approved_by`, `created_at`.

### `method_rubrics`

`id`, `methodology_id`, `version`, `status`, `input_schema_version`, `normalization_rules_json`, `subweights_json`, `minimum_evidence_json`, `approved_by`, `effective_at`, `created_at`.

### `method_scores`

`id`, `market_id`, `market_definition_version_id`, `methodology_id`, `research_profile`, `scoring_configuration_id`, `input_cutoff_at`, `input_hash`, `computed_score` nullable, `computed_breakdown_json`, `reviewed_score` nullable, `review_status`, `reviewer_id` nullable, `reviewed_at` nullable, `suggested_confidence_numeric` nullable, `suggested_confidence_label` nullable, `reviewed_confidence_numeric` nullable, `reviewed_confidence_label` nullable, `created_at`, `supersedes_id` nullable.

### `method_score_evidence`

`id`, `method_score_id`, `evidence_item_id` nullable, `method_record_type` nullable, `method_record_id` nullable, `calculation_component`, `relationship`, `created_at`.

At least one evidence or structured method record is required for an approved non-null score.

### `score_overrides`

`id`, `method_score_id`, `from_score`, `to_score`, `delta`, `reason`, `reviewer_id`, `is_substantial`, `approved_by` nullable, `created_at`.

Override evidence uses `evidence_links` or a dedicated join table.

### `evidence_requirements` and `evidence_gap_results`

Requirement: `id`, `methodology_id`, `research_profile`, `version`, `requirement_key`, `description`, `deterministic_rule_json`, `priority`, `next_action_template`.  
Result: `id`, `market_id`, `requirement_id`, `input_hash`, `state`, `reason_json`, `calculated_at`, `snapshot_id` nullable.

### `market_score_snapshots`

`id`, `market_id`, `market_definition_version_id`, `research_profile`, `scoring_configuration_id`, `input_cutoff_at`, `method_score_ids_json`, `computed_market_score` nullable, `reviewed_market_score` nullable, `market_confidence_numeric` nullable, `market_confidence_label` nullable, `completeness_json`, `veto_state_json`, `calculation_json`, `status`, `created_by`, `created_at`.

### `red_flags`

`id`, `market_id`, `veto_type`, `severity`, `status`, `description`, `owner_id`, `resolution`, `created_at`, `updated_at`, `resolved_at`. Supporting evidence is linked explicitly.

### `veto_exceptions`

`id`, `red_flag_id`, `gate`, `founder_id`, `rationale`, `review_due_at`, `created_at`. The original red flag remains visible.

### `stage_gate_decisions`

`id`, `market_id`, `from_stage`, `gate`, `score_snapshot_id`, `engine_result`, `failed_conditions_json`, `human_decision`, `decision_reason`, `decided_by`, `decided_at`, `to_stage` nullable, `supersedes_id` nullable.

Eligible results do not transition stages without this explicit decision.

## 10. Audit and versioning

### `audit_events`

Append-only: `id`, `organization_id`, `actor_user_id` nullable, `actor_type`, `acting_role` nullable, `event_type`, `entity_type`, `entity_id`, `entity_version` nullable, `before_json` nullable, `after_json` nullable, `reason` nullable, `correlation_id`, `occurred_at`.

Secrets, full sensitive transcripts, and unnecessary personal data must not be copied into audit payloads.

### Required audited events

Market definition/hypothesis changes, source-policy changes, collection runs, document retention actions, analysis/prompt/model/taxonomy versions, evidence reviews, cluster changes, rubric/configuration changes, score calculations and approvals, overrides, confidence changes, red flags/exceptions, experiment changes, and stage/final decisions.

## 11. Integrity constraints

- Every market belongs to one organization.
- A market owner/reviewer must belong to that organization.
- All child evidence must resolve to the same organization and market.
- Each analysis output references exactly one input context and complete version tuple.
- A `method_score` methodology matches all linked method evidence.
- Active overall weights total 100%; active subweights total 100% where applicable.
- An approved score has a reviewer and linked evidence.
- A final snapshot contains all ten compatible approved method scores.
- A stage transition references a snapshot and records engine result plus human decision.
- Aggregate counts exclude rejected and duplicate evidence according to their versioned rules.
- Historical snapshots, analysis runs, audit events, and decisions are not updated in place.

## 12. Indexing and partition considerations

Phase 1 should create ordinary indexes for tenant/market/time access, source/external ID, hashes, job status, analysis versions, review state, and score snapshots. Add pgvector indexes only after representative volume and recall/latency testing. Consider time or tenant partitioning for raw documents/audit events later; do not introduce it before workload evidence justifies it.
