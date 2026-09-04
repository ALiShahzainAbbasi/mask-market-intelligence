from datetime import datetime
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mask_api.job_queue.domain import JobStatus
from mask_api.persistence.base import Base, CreatedAt, enum_type


class JobRecord(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "job_type",
            "idempotency_key",
            "configuration_version",
            name="uq_job_idempotency",
            postgresql_nulls_not_distinct=True,
        ),
        ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_job_organization"),
        ForeignKeyConstraint(
            ["organization_id", "market_id"],
            ["markets.organization_id", "markets.id"],
            name="fk_job_market_scope",
        ),
        CheckConstraint(
            "market_id IS NULL OR organization_id IS NOT NULL", name="ck_job_market_scope"
        ),
        CheckConstraint("attempt_count BETWEEN 0 AND max_attempts", name="ck_job_attempts"),
        CheckConstraint("max_attempts BETWEEN 1 AND 10", name="ck_job_attempt_limit"),
        CheckConstraint(
            "progress_current >= 0 AND (progress_total IS NULL OR "
            "progress_current <= progress_total)",
            name="ck_job_progress",
        ),
        CheckConstraint("length(input_hash) = 64", name="ck_job_input_hash"),
        CheckConstraint("jsonb_typeof(input_reference) = 'object'", name="ck_job_input_reference"),
        CheckConstraint(
            "jsonb_typeof(configuration_versions) = 'object'",
            name="ck_job_configuration_versions",
        ),
        CheckConstraint(
            "output_reference IS NULL OR jsonb_typeof(output_reference) = 'object'",
            name="ck_job_output_reference",
        ),
        CheckConstraint(
            "(status = 'running') = (lease_owner IS NOT NULL AND lease_token IS NOT NULL "
            "AND lease_expires_at IS NOT NULL)",
            name="ck_job_active_lease",
        ),
        Index("ix_job_claim", "status", "available_at", "queued_at"),
        Index("ix_job_tenant_market", "organization_id", "market_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID | None] = mapped_column(Uuid)
    market_id: Mapped[UUID | None] = mapped_column(Uuid)
    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        enum_type(JobStatus, "ck_job_status"), server_default="queued", nullable=False
    )
    idempotency_key: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    configuration_version: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration_versions: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    input_reference: Mapped[dict[str, JsonValue]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_reference: Mapped[dict[str, JsonValue] | None] = mapped_column(JSONB)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    progress_current: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    progress_total: Mapped[int | None] = mapped_column(Integer)
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[UUID | None] = mapped_column(Uuid)
    lease_token: Mapped[UUID | None] = mapped_column(Uuid)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)


class WorkerHeartbeat(CreatedAt, Base):
    __tablename__ = "worker_heartbeats"
    worker_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
