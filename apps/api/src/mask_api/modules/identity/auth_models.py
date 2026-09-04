from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from mask_api.modules.identity.domain import IdentityEventOutcome, IdentityEventType
from mask_api.persistence.base import Base, CreatedAt, MutableTimestamps, UUIDPrimaryKey, enum_type


class UserCredential(MutableTimestamps, Base):
    __tablename__ = "user_credentials"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["users.organization_id", "users.id"],
            name="fk_credential_tenant_user",
        ),
        CheckConstraint(
            "length(password_hash) BETWEEN 20 AND 1000", name="ck_credential_password_hash"
        ),
        CheckConstraint("failed_login_count >= 0", name="ck_credential_failure_count"),
    )
    user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    password_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_successful_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ServerSession(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "server_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["users.organization_id", "users.id"],
            name="fk_session_tenant_user",
        ),
        UniqueConstraint("token_hash", name="uq_session_token_hash"),
        UniqueConstraint("rotated_from_id", name="uq_session_rotation_source"),
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="ck_session_token_hash"),
        CheckConstraint("csrf_hash ~ '^[0-9a-f]{64}$'", name="ck_session_csrf_hash"),
        CheckConstraint(
            "authenticated_at <= created_at AND created_at < expires_at",
            name="ck_session_timeline",
        ),
        CheckConstraint(
            "(revoked_at IS NULL) = (revocation_reason IS NULL)",
            name="ck_session_revocation_pair",
        ),
        Index("ix_session_tenant_user", "organization_id", "user_id"),
        Index("ix_session_expiry", "expires_at"),
    )
    organization_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    authenticated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revocation_reason: Mapped[str | None] = mapped_column(String(64))
    rotated_from_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("server_sessions.id", name="fk_session_rotation_source")
    )


class IdentitySecurityEvent(UUIDPrimaryKey, Base):
    __tablename__ = "identity_security_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["users.organization_id", "users.id"],
            name="fk_identity_event_tenant_user",
        ),
        CheckConstraint("length(btrim(reason_code)) > 0", name="ck_identity_event_reason"),
        Index("ix_identity_event_tenant_time", "organization_id", "occurred_at"),
        Index("ix_identity_event_correlation", "correlation_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    event_type: Mapped[IdentityEventType] = mapped_column(
        enum_type(IdentityEventType, "ck_identity_event_type"), nullable=False
    )
    outcome: Mapped[IdentityEventOutcome] = mapped_column(
        enum_type(IdentityEventOutcome, "ck_identity_event_outcome"), nullable=False
    )
    organization_id: Mapped[UUID | None] = mapped_column(Uuid)
    user_id: Mapped[UUID | None] = mapped_column(Uuid)
    session_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("server_sessions.id", name="fk_identity_event_session")
    )
    correlation_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
