from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UUIDPrimaryKey:
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)


class CreatedAt:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MutableTimestamps(CreatedAt):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


def enum_type(values: type[StrEnum], constraint_name: str) -> Enum:
    """Portable VARCHAR + CHECK; domain values remain framework-independent."""
    return Enum(
        values,
        values_callable=lambda members: [member.value for member in members],
        name=constraint_name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        length=32,
    )
