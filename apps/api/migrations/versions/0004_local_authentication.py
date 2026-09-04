"""Local credentials, hashed server sessions, and identity security events.

Frozen PostgreSQL DDL generated/reviewed from the P02-02 metadata. This
historical migration intentionally imports no application models.
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

UPGRADE_SQL = (
    """CREATE TABLE user_credentials (
        user_id UUID NOT NULL,
        organization_id UUID NOT NULL,
        password_hash TEXT NOT NULL,
        password_changed_at TIMESTAMP WITH TIME ZONE NOT NULL,
        failed_login_count INTEGER DEFAULT '0' NOT NULL,
        locked_until TIMESTAMP WITH TIME ZONE,
        last_failed_at TIMESTAMP WITH TIME ZONE,
        last_successful_login_at TIMESTAMP WITH TIME ZONE,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (user_id),
        CONSTRAINT fk_credential_tenant_user FOREIGN KEY(organization_id, user_id)
            REFERENCES users (organization_id, id),
        CONSTRAINT ck_credential_password_hash CHECK
            (length(password_hash) BETWEEN 20 AND 1000),
        CONSTRAINT ck_credential_failure_count CHECK (failed_login_count >= 0)
)""",
    """CREATE TABLE server_sessions (
        organization_id UUID NOT NULL,
        user_id UUID NOT NULL,
        token_hash VARCHAR(64) NOT NULL,
        csrf_hash VARCHAR(64) NOT NULL,
        authenticated_at TIMESTAMP WITH TIME ZONE NOT NULL,
        expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
        revoked_at TIMESTAMP WITH TIME ZONE,
        revocation_reason VARCHAR(64),
        rotated_from_id UUID,
        id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT fk_session_tenant_user FOREIGN KEY(organization_id, user_id)
            REFERENCES users (organization_id, id),
        CONSTRAINT uq_session_token_hash UNIQUE (token_hash),
        CONSTRAINT uq_session_rotation_source UNIQUE (rotated_from_id),
        CONSTRAINT ck_session_token_hash CHECK (token_hash ~ '^[0-9a-f]{64}$'),
        CONSTRAINT ck_session_csrf_hash CHECK (csrf_hash ~ '^[0-9a-f]{64}$'),
        CONSTRAINT ck_session_timeline CHECK
            (authenticated_at <= created_at AND created_at < expires_at),
        CONSTRAINT ck_session_revocation_pair CHECK
            ((revoked_at IS NULL) = (revocation_reason IS NULL)),
        CONSTRAINT fk_session_rotation_source FOREIGN KEY(rotated_from_id)
            REFERENCES server_sessions (id)
)""",
    "CREATE INDEX ix_session_expiry ON server_sessions (expires_at)",
    "CREATE INDEX ix_session_tenant_user ON server_sessions (organization_id, user_id)",
    """CREATE TABLE identity_security_events (
        id UUID NOT NULL,
        event_type VARCHAR(32) NOT NULL,
        outcome VARCHAR(32) NOT NULL,
        organization_id UUID,
        user_id UUID,
        session_id UUID,
        correlation_id UUID NOT NULL,
        reason_code VARCHAR(64) NOT NULL,
        occurred_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT fk_identity_event_tenant_user FOREIGN KEY(organization_id, user_id)
            REFERENCES users (organization_id, id),
        CONSTRAINT ck_identity_event_reason CHECK (length(btrim(reason_code)) > 0),
        CONSTRAINT ck_identity_event_type CHECK (event_type IN
            ('owner_bootstrapped', 'login_succeeded', 'login_failed',
             'login_throttled', 'session_rotated', 'session_revoked')),
        CONSTRAINT ck_identity_event_outcome CHECK
            (outcome IN ('succeeded', 'denied')),
        CONSTRAINT fk_identity_event_session FOREIGN KEY(session_id)
            REFERENCES server_sessions (id)
)""",
    "CREATE INDEX ix_identity_event_correlation ON identity_security_events (correlation_id)",
    """CREATE INDEX ix_identity_event_tenant_time
ON identity_security_events (organization_id, occurred_at)""",
)


def upgrade() -> None:
    for statement in UPGRADE_SQL:
        op.execute(statement)
    op.execute("GRANT SELECT, INSERT, UPDATE ON user_credentials, server_sessions TO mask_app")
    op.execute("GRANT SELECT, INSERT ON identity_security_events TO mask_app")


def downgrade() -> None:
    op.drop_table("identity_security_events")
    op.drop_table("server_sessions")
    op.drop_table("user_credentials")
