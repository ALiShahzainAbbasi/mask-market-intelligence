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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mask_api.modules.markets.domain import (
    HypothesisStatus,
    MarketStage,
    MarketStatus,
    ResearchPlanStatus,
)
from mask_api.persistence.base import Base, CreatedAt, MutableTimestamps, UUIDPrimaryKey, enum_type


class DefinitionFields:
    """The comparison boundary is copied into each immutable definition version."""

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    submarket: Mapped[str] = mapped_column(String(200), nullable=False)
    geography: Mapped[str] = mapped_column(String(300), nullable=False)
    company_size_definition: Mapped[str] = mapped_column(String(1000), nullable=False)
    likely_buyer: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, server_default="", nullable=False)


class Market(UUIDPrimaryKey, MutableTimestamps, DefinitionFields, Base):
    __tablename__ = "markets"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_market_tenant_id"),
        ForeignKeyConstraint(
            ["organization_id", "research_owner_id"],
            ["users.organization_id", "users.id"],
            name="fk_market_owner_tenant",
        ),
        ForeignKeyConstraint(
            ["organization_id", "reviewer_id"],
            ["users.organization_id", "users.id"],
            name="fk_market_reviewer_tenant",
        ),
        ForeignKeyConstraint(
            ["organization_id", "id", "current_definition_version_id"],
            [
                "market_definition_versions.organization_id",
                "market_definition_versions.market_id",
                "market_definition_versions.id",
            ],
            name="fk_market_current_definition",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("version >= 1", name="ck_market_version"),
        CheckConstraint(
            "length(btrim(name)) > 0 AND length(btrim(submarket)) > 0 "
            "AND length(btrim(geography)) > 0 AND length(btrim(company_size_definition)) > 0 "
            "AND length(btrim(likely_buyer)) > 0",
            name="ck_market_definition_fields",
        ),
        Index("ix_market_tenant_status", "organization_id", "status"),
    )
    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", name="fk_market_organization"), nullable=False
    )
    research_owner_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    reviewer_id: Mapped[UUID | None] = mapped_column(Uuid)
    current_definition_version_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    stage: Mapped[MarketStage] = mapped_column(
        enum_type(MarketStage, "ck_market_stage"), server_default="broad_screen", nullable=False
    )
    status: Mapped[MarketStatus] = mapped_column(
        enum_type(MarketStatus, "ck_market_status"), server_default="active", nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, server_default="1", nullable=False)
    __mapper_args__ = {"version_id_col": version}


class MarketDefinitionVersion(UUIDPrimaryKey, CreatedAt, DefinitionFields, Base):
    __tablename__ = "market_definition_versions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "market_id", "id", name="uq_definition_tenant_market_id"
        ),
        UniqueConstraint(
            "organization_id", "market_id", "version_number", name="uq_definition_number"
        ),
        ForeignKeyConstraint(
            ["organization_id", "market_id"],
            ["markets.organization_id", "markets.id"],
            name="fk_definition_tenant_market",
        ),
        ForeignKeyConstraint(
            ["organization_id", "created_by"],
            ["users.organization_id", "users.id"],
            name="fk_definition_author_tenant",
        ),
        CheckConstraint("version_number >= 1", name="ck_definition_version"),
        CheckConstraint("length(btrim(change_reason)) > 0", name="ck_definition_reason"),
        CheckConstraint(
            "length(btrim(name)) > 0 AND length(btrim(submarket)) > 0 "
            "AND length(btrim(geography)) > 0 AND length(btrim(company_size_definition)) > 0 "
            "AND length(btrim(likely_buyer)) > 0",
            name="ck_definition_fields",
        ),
    )
    organization_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    market_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    change_reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)


class MarketHypothesis(UUIDPrimaryKey, MutableTimestamps, Base):
    __tablename__ = "market_hypotheses"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "market_id", "market_definition_version_id"],
            [
                "market_definition_versions.organization_id",
                "market_definition_versions.market_id",
                "market_definition_versions.id",
            ],
            name="fk_hypothesis_definition_scope",
        ),
        ForeignKeyConstraint(
            ["organization_id", "created_by"],
            ["users.organization_id", "users.id"],
            name="fk_hypothesis_author_tenant",
        ),
        CheckConstraint("length(btrim(hypothesis_type)) > 0", name="ck_hypothesis_type"),
        CheckConstraint(
            "length(btrim(statement)) BETWEEN 1 AND 10000", name="ck_hypothesis_statement"
        ),
        Index("ix_hypothesis_tenant_market", "organization_id", "market_id"),
    )
    organization_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    market_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    market_definition_version_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    hypothesis_type: Mapped[str] = mapped_column(String(80), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[HypothesisStatus] = mapped_column(
        enum_type(HypothesisStatus, "ck_hypothesis_status"),
        server_default="proposed",
        nullable=False,
    )
    created_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)


class ResearchPlan(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "research_plans"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "market_id", "market_definition_version_id"],
            [
                "market_definition_versions.organization_id",
                "market_definition_versions.market_id",
                "market_definition_versions.id",
            ],
            name="fk_plan_definition_scope",
        ),
        ForeignKeyConstraint(
            ["organization_id", "created_by"],
            ["users.organization_id", "users.id"],
            name="fk_plan_author_tenant",
        ),
        ForeignKeyConstraint(
            ["organization_id", "approved_by"],
            ["users.organization_id", "users.id"],
            name="fk_plan_approver_tenant",
        ),
        CheckConstraint(
            "(approved_by IS NULL) = (approved_at IS NULL)", name="ck_plan_approval_pair"
        ),
        CheckConstraint(
            "status <> 'approved' OR approved_by IS NOT NULL", name="ck_plan_approved_actor"
        ),
        CheckConstraint(
            "status <> 'draft' OR approved_by IS NULL", name="ck_plan_draft_unapproved"
        ),
        CheckConstraint(
            "length(btrim(research_profile)) > 0 AND length(btrim(methodology_version)) > 0",
            name="ck_plan_versions",
        ),
        CheckConstraint(
            "jsonb_typeof(required_evidence_json) = 'object'", name="ck_plan_evidence_object"
        ),
        Index("ix_plan_tenant_market", "organization_id", "market_id"),
    )
    organization_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    market_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    market_definition_version_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    research_profile: Mapped[str] = mapped_column(String(100), nullable=False)
    methodology_version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[ResearchPlanStatus] = mapped_column(
        enum_type(ResearchPlanStatus, "ck_plan_status"), server_default="draft", nullable=False
    )
    required_evidence_json: Mapped[dict[str, object]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb"), nullable=False
    )
    created_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    approved_by: Mapped[UUID | None] = mapped_column(Uuid)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
