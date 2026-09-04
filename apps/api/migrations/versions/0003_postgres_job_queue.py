"""Replace the Redis/Celery smoke path with durable PostgreSQL jobs.

Frozen PostgreSQL DDL generated and reviewed from the queue metadata. This
migration preserves existing infrastructure smoke rows before removing their
single-purpose table. Do not import live models into historical migrations.
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

UPGRADE_SQL = (
    """CREATE TABLE jobs (
        id UUID NOT NULL,
        organization_id UUID,
        market_id UUID,
        job_type VARCHAR(100) NOT NULL,
        status VARCHAR(32) DEFAULT 'queued' NOT NULL,
        idempotency_key UUID NOT NULL,
        schema_version VARCHAR(32) NOT NULL,
        configuration_version VARCHAR(64) NOT NULL,
        configuration_versions JSONB DEFAULT '{}'::jsonb NOT NULL,
        input_reference JSONB DEFAULT '{}'::jsonb NOT NULL,
        input_hash VARCHAR(64) NOT NULL,
        output_reference JSONB,
        attempt_count INTEGER DEFAULT '0' NOT NULL,
        max_attempts INTEGER DEFAULT '3' NOT NULL,
        progress_current INTEGER DEFAULT '0' NOT NULL,
        progress_total INTEGER,
        queued_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        available_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        started_at TIMESTAMP WITH TIME ZONE,
        heartbeat_at TIMESTAMP WITH TIME ZONE,
        completed_at TIMESTAMP WITH TIME ZONE,
        lease_owner UUID,
        lease_token UUID,
        lease_expires_at TIMESTAMP WITH TIME ZONE,
        cancel_requested_at TIMESTAMP WITH TIME ZONE,
        error_code VARCHAR(64),
        error_message TEXT,
        correlation_id UUID NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_job_idempotency UNIQUE NULLS NOT DISTINCT
            (organization_id, job_type, idempotency_key, configuration_version),
        CONSTRAINT fk_job_organization FOREIGN KEY(organization_id)
            REFERENCES organizations (id),
        CONSTRAINT fk_job_market_scope FOREIGN KEY(organization_id, market_id)
            REFERENCES markets (organization_id, id),
        CONSTRAINT ck_job_market_scope CHECK
            (market_id IS NULL OR organization_id IS NOT NULL),
        CONSTRAINT ck_job_attempts CHECK (attempt_count BETWEEN 0 AND max_attempts),
        CONSTRAINT ck_job_attempt_limit CHECK (max_attempts BETWEEN 1 AND 10),
        CONSTRAINT ck_job_progress CHECK (progress_current >= 0 AND
            (progress_total IS NULL OR progress_current <= progress_total)),
        CONSTRAINT ck_job_input_hash CHECK (length(input_hash) = 64),
        CONSTRAINT ck_job_input_reference CHECK
            (jsonb_typeof(input_reference) = 'object'),
        CONSTRAINT ck_job_configuration_versions CHECK
            (jsonb_typeof(configuration_versions) = 'object'),
        CONSTRAINT ck_job_output_reference CHECK
            (output_reference IS NULL OR jsonb_typeof(output_reference) = 'object'),
        CONSTRAINT ck_job_active_lease CHECK ((status = 'running') =
            (lease_owner IS NOT NULL AND lease_token IS NOT NULL AND
             lease_expires_at IS NOT NULL)),
        CONSTRAINT ck_job_status CHECK (status IN
            ('queued', 'running', 'partial', 'succeeded', 'failed', 'cancelled'))
    )""",
    "CREATE INDEX ix_job_tenant_market ON jobs (organization_id, market_id)",
    "CREATE INDEX ix_job_claim ON jobs (status, available_at, queued_at)",
    """CREATE TABLE worker_heartbeats (
        worker_id UUID NOT NULL,
        started_at TIMESTAMP WITH TIME ZONE NOT NULL,
        heartbeat_at TIMESTAMP WITH TIME ZONE NOT NULL,
        stopped_at TIMESTAMP WITH TIME ZONE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (worker_id)
    )""",
)


def upgrade() -> None:
    for statement in UPGRADE_SQL:
        op.execute(statement)
    op.execute(
        """INSERT INTO jobs (
            id, organization_id, market_id, job_type, status, idempotency_key,
            schema_version, configuration_version, configuration_versions,
            input_reference, input_hash, output_reference, attempt_count,
            max_attempts, progress_current, progress_total, queued_at,
            available_at, completed_at, correlation_id
        )
        SELECT id, NULL, NULL, 'infrastructure.smoke', status, idempotency_key,
            '1', '1', '{}'::jsonb, '{}'::jsonb,
            'b08d5c96ca438681d6569d00fb7ba2ef8a54fed04fcbada55b7074a6cd715ef7',
            CASE WHEN status = 'succeeded'
                THEN jsonb_build_object('execution_count', execution_count)
                ELSE NULL END,
            execution_count, 3, execution_count, 1, created_at, created_at,
            completed_at, correlation_id
        FROM infrastructure_smoke_jobs"""
    )
    op.drop_table("infrastructure_smoke_jobs")
    op.execute("GRANT SELECT, INSERT, UPDATE ON jobs, worker_heartbeats TO mask_app")


def downgrade() -> None:
    op.execute(
        """CREATE TABLE infrastructure_smoke_jobs (
            id UUID NOT NULL,
            idempotency_key UUID NOT NULL,
            correlation_id UUID NOT NULL,
            status VARCHAR(16) DEFAULT 'queued' NOT NULL,
            execution_count INTEGER DEFAULT '0' NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            completed_at TIMESTAMP WITH TIME ZONE,
            PRIMARY KEY (id),
            UNIQUE (idempotency_key),
            CONSTRAINT ck_smoke_status CHECK (status IN ('queued', 'succeeded')),
            CONSTRAINT ck_smoke_execution_count CHECK
                (execution_count BETWEEN 0 AND 1)
        )"""
    )
    op.execute(
        """INSERT INTO infrastructure_smoke_jobs (
            id, idempotency_key, correlation_id, status, execution_count,
            created_at, completed_at
        )
        SELECT id, idempotency_key, correlation_id,
            CASE WHEN status = 'succeeded' THEN 'succeeded' ELSE 'queued' END,
            CASE WHEN status = 'succeeded' THEN 1 ELSE 0 END,
            queued_at,
            CASE WHEN status = 'succeeded' THEN completed_at ELSE NULL END
        FROM jobs WHERE job_type = 'infrastructure.smoke'"""
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON infrastructure_smoke_jobs TO mask_app")
    op.drop_table("worker_heartbeats")
    op.drop_table("jobs")
