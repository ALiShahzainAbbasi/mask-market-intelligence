"""Identity and market registry foundation; no authentication endpoints.

Frozen PostgreSQL DDL generated/reviewed from Phase 2 metadata. Do not import
live models into historical migrations. Integration execution is still required.
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

UPGRADE_SQL = (
    """CREATE TABLE organizations (
        name VARCHAR(200) NOT NULL,
        status VARCHAR(32) DEFAULT 'active' NOT NULL,
        id UUID NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT ck_organization_name CHECK (length(btrim(name)) > 0),
        CONSTRAINT ck_organization_status CHECK (status IN ('active', 'suspended'))
)""",
    """CREATE TABLE users (
        organization_id UUID NOT NULL,
        name VARCHAR(200) NOT NULL,
        email VARCHAR(254) NOT NULL,
        status VARCHAR(32) DEFAULT 'invited' NOT NULL,
        id UUID NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_user_tenant_id UNIQUE (organization_id, id),
        CONSTRAINT uq_user_tenant_email UNIQUE (organization_id, email),
        CONSTRAINT ck_user_name CHECK (length(btrim(name)) > 0),
        CONSTRAINT ck_user_normalized_email CHECK (email = lower(btrim(email)) AND
    length(email) > 3),
        CONSTRAINT fk_user_organization FOREIGN KEY(organization_id) REFERENCES
    organizations (id),
        CONSTRAINT ck_user_status CHECK (status IN ('invited', 'active', 'suspended'))
)""",
    """CREATE TABLE user_roles (
        organization_id UUID NOT NULL,
        user_id UUID NOT NULL,
        role VARCHAR(32) NOT NULL,
        id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT fk_role_tenant_user FOREIGN KEY(organization_id, user_id) REFERENCES
    users (organization_id, id),
        CONSTRAINT uq_user_role UNIQUE (organization_id, user_id, role),
        CONSTRAINT ck_user_role CHECK (role IN ('researcher', 'reviewer', 'sales',
    'technical', 'founder', 'admin'))
)""",
    """CREATE TABLE markets (
        organization_id UUID NOT NULL,
        research_owner_id UUID NOT NULL,
        reviewer_id UUID,
        current_definition_version_id UUID NOT NULL,
        stage VARCHAR(32) DEFAULT 'broad_screen' NOT NULL,
        status VARCHAR(32) DEFAULT 'active' NOT NULL,
        version INTEGER DEFAULT '1' NOT NULL,
        id UUID NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        name VARCHAR(200) NOT NULL,
        submarket VARCHAR(200) NOT NULL,
        geography VARCHAR(300) NOT NULL,
        company_size_definition VARCHAR(1000) NOT NULL,
        likely_buyer VARCHAR(300) NOT NULL,
        description TEXT DEFAULT '' NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_market_tenant_id UNIQUE (organization_id, id),
        CONSTRAINT fk_market_owner_tenant FOREIGN KEY(organization_id, research_owner_id)
    REFERENCES users (organization_id, id),
        CONSTRAINT fk_market_reviewer_tenant FOREIGN KEY(organization_id, reviewer_id)
    REFERENCES users (organization_id, id),
        CONSTRAINT ck_market_version CHECK (version >= 1),
        CONSTRAINT ck_market_definition_fields CHECK (length(btrim(name)) > 0 AND
    length(btrim(submarket)) > 0 AND length(btrim(geography)) > 0 AND
    length(btrim(company_size_definition)) > 0 AND length(btrim(likely_buyer)) > 0),
        CONSTRAINT fk_market_organization FOREIGN KEY(organization_id) REFERENCES
    organizations (id),
        CONSTRAINT ck_market_stage CHECK (stage IN ('broad_screen', 'deep_research',
    'live_validation', 'finalist', 'selected', 'rejected')),
        CONSTRAINT ck_market_status CHECK (status IN ('active', 'hold', 'archived'))
)""",
    """CREATE INDEX ix_market_tenant_status ON markets (organization_id, status)""",
    """CREATE TABLE market_definition_versions (
        organization_id UUID NOT NULL,
        market_id UUID NOT NULL,
        version_number INTEGER NOT NULL,
        change_reason TEXT NOT NULL,
        created_by UUID NOT NULL,
        id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        name VARCHAR(200) NOT NULL,
        submarket VARCHAR(200) NOT NULL,
        geography VARCHAR(300) NOT NULL,
        company_size_definition VARCHAR(1000) NOT NULL,
        likely_buyer VARCHAR(300) NOT NULL,
        description TEXT DEFAULT '' NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_definition_tenant_market_id UNIQUE (organization_id, market_id, id),
        CONSTRAINT uq_definition_number UNIQUE (organization_id, market_id, version_number),
        CONSTRAINT fk_definition_tenant_market FOREIGN KEY(organization_id, market_id)
    REFERENCES markets (organization_id, id),
        CONSTRAINT fk_definition_author_tenant FOREIGN KEY(organization_id, created_by)
    REFERENCES users (organization_id, id),
        CONSTRAINT ck_definition_version CHECK (version_number >= 1),
        CONSTRAINT ck_definition_reason CHECK (length(btrim(change_reason)) > 0),
        CONSTRAINT ck_definition_fields CHECK (length(btrim(name)) > 0 AND
    length(btrim(submarket)) > 0 AND length(btrim(geography)) > 0 AND
    length(btrim(company_size_definition)) > 0 AND length(btrim(likely_buyer)) > 0)
)""",
    """CREATE TABLE market_hypotheses (
        organization_id UUID NOT NULL,
        market_id UUID NOT NULL,
        market_definition_version_id UUID NOT NULL,
        hypothesis_type VARCHAR(80) NOT NULL,
        statement TEXT NOT NULL,
        status VARCHAR(32) DEFAULT 'proposed' NOT NULL,
        created_by UUID NOT NULL,
        id UUID NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT fk_hypothesis_definition_scope FOREIGN KEY(organization_id, market_id,
    market_definition_version_id) REFERENCES market_definition_versions (organization_id,
    market_id, id),
        CONSTRAINT fk_hypothesis_author_tenant FOREIGN KEY(organization_id, created_by)
    REFERENCES users (organization_id, id),
        CONSTRAINT ck_hypothesis_type CHECK (length(btrim(hypothesis_type)) > 0),
        CONSTRAINT ck_hypothesis_statement CHECK (length(btrim(statement)) BETWEEN 1 AND
    10000),
        CONSTRAINT ck_hypothesis_status CHECK (status IN ('proposed', 'supported',
    'contradicted', 'inconclusive', 'retired'))
)""",
    """CREATE INDEX ix_hypothesis_tenant_market
ON market_hypotheses (organization_id, market_id)""",
    """CREATE TABLE research_plans (
        organization_id UUID NOT NULL,
        market_id UUID NOT NULL,
        market_definition_version_id UUID NOT NULL,
        research_profile VARCHAR(100) NOT NULL,
        methodology_version VARCHAR(100) NOT NULL,
        status VARCHAR(32) DEFAULT 'draft' NOT NULL,
        required_evidence_json JSONB DEFAULT '{}'::jsonb NOT NULL,
        created_by UUID NOT NULL,
        approved_by UUID,
        approved_at TIMESTAMP WITH TIME ZONE,
        id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT fk_plan_definition_scope FOREIGN KEY(organization_id, market_id,
    market_definition_version_id) REFERENCES market_definition_versions (organization_id,
    market_id, id),
        CONSTRAINT fk_plan_author_tenant FOREIGN KEY(organization_id, created_by) REFERENCES
    users (organization_id, id),
        CONSTRAINT fk_plan_approver_tenant FOREIGN KEY(organization_id, approved_by)
    REFERENCES users (organization_id, id),
        CONSTRAINT ck_plan_approval_pair CHECK ((approved_by IS NULL) = (approved_at IS
    NULL)),
        CONSTRAINT ck_plan_approved_actor CHECK (status <> 'approved' OR approved_by IS NOT
    NULL),
        CONSTRAINT ck_plan_draft_unapproved CHECK (status <> 'draft' OR approved_by IS
    NULL),
        CONSTRAINT ck_plan_versions CHECK (length(btrim(research_profile)) > 0 AND
    length(btrim(methodology_version)) > 0),
        CONSTRAINT ck_plan_evidence_object CHECK (jsonb_typeof(required_evidence_json) =
    'object'),
        CONSTRAINT ck_plan_status CHECK (status IN ('draft', 'approved', 'retired'))
)""",
    """CREATE INDEX ix_plan_tenant_market ON research_plans (organization_id, market_id)""",
    """ALTER TABLE markets ADD CONSTRAINT fk_market_current_definition FOREIGN KEY(organization_id,
    id, current_definition_version_id) REFERENCES market_definition_versions
    (organization_id, market_id, id) DEFERRABLE INITIALLY DEFERRED""",
)


def upgrade() -> None:
    for statement in UPGRADE_SQL:
        op.execute(statement)
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON organizations, users, user_roles, markets, "
        "market_hypotheses, research_plans TO mask_app"
    )
    # Definitions are append-only for the application role, including direct SQL.
    op.execute("GRANT SELECT, INSERT ON market_definition_versions TO mask_app")


def downgrade() -> None:
    op.drop_constraint("fk_market_current_definition", "markets", type_="foreignkey")
    for table in (
        "research_plans",
        "market_hypotheses",
        "market_definition_versions",
        "markets",
        "user_roles",
        "users",
        "organizations",
    ):
        op.drop_table(table)
