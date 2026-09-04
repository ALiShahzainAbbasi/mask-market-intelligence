from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from mask_api.modules.identity.domain import OrganizationStatus, Role, UserStatus
from mask_api.persistence.base import Base, CreatedAt, MutableTimestamps, UUIDPrimaryKey, enum_type


class Organization(UUIDPrimaryKey, MutableTimestamps, Base):
    __tablename__ = "organizations"
    __table_args__ = (CheckConstraint("length(btrim(name)) > 0", name="ck_organization_name"),)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[OrganizationStatus] = mapped_column(
        enum_type(OrganizationStatus, "ck_organization_status"),
        server_default="active",
        nullable=False,
    )


class User(UUIDPrimaryKey, MutableTimestamps, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_user_tenant_id"),
        UniqueConstraint("organization_id", "email", name="uq_user_tenant_email"),
        CheckConstraint("length(btrim(name)) > 0", name="ck_user_name"),
        CheckConstraint(
            "email = lower(btrim(email)) AND length(email) > 3", name="ck_user_normalized_email"
        ),
    )
    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", name="fk_user_organization"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        enum_type(UserStatus, "ck_user_status"), server_default="invited", nullable=False
    )


class UserRole(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["users.organization_id", "users.id"],
            name="fk_role_tenant_user",
        ),
        UniqueConstraint("organization_id", "user_id", "role", name="uq_user_role"),
    )
    organization_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    role: Mapped[Role] = mapped_column(enum_type(Role, "ck_user_role"), nullable=False)
