"""Enable pgvector and add idempotent infrastructure-only smoke jobs."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "infrastructure_smoke_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False, unique=True),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("execution_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('queued', 'succeeded')", name="ck_smoke_status"),
        sa.CheckConstraint("execution_count BETWEEN 0 AND 1", name="ck_smoke_execution_count"),
    )
    op.execute("GRANT USAGE ON SCHEMA public TO mask_app")
    op.execute("GRANT SELECT, INSERT, UPDATE ON infrastructure_smoke_jobs TO mask_app")
    op.execute("GRANT SELECT ON alembic_version TO mask_app")


def downgrade() -> None:
    op.drop_table("infrastructure_smoke_jobs")
    # Keep shared extension installed; deleting it could destroy future vectors.
