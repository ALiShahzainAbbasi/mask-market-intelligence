"""Identity-owned persistence. Read-only; no account bootstrap or role mutations."""

from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from mask_api.modules.identity.contracts import Membership
from mask_api.modules.identity.errors import IdentityUnavailable
from mask_api.modules.identity.models import Organization, User, UserRole


class SQLAlchemyMembershipReader:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self.sessions = sessions

    def get(self, organization_id: UUID, user_id: UUID) -> Membership | None:
        # One statement sees statuses and roles together; select scalar columns
        # so a long-lived ORM identity map cannot return a stale role collection.
        statement = (
            select(Organization.status, User.status, UserRole.role)
            .select_from(User)
            .join(Organization, Organization.id == User.organization_id)
            .outerjoin(
                UserRole,
                and_(
                    UserRole.organization_id == User.organization_id,
                    UserRole.user_id == User.id,
                ),
            )
            .where(User.organization_id == organization_id, User.id == user_id)
        )
        try:
            with self.sessions() as session:
                rows = session.execute(statement).all()
            if not rows:
                return None
            return Membership(
                organization_id=organization_id,
                user_id=user_id,
                organization_status=rows[0][0],
                user_status=rows[0][1],
                roles=frozenset(row[2] for row in rows if row[2] is not None),
            )
        except (SQLAlchemyError, ValueError):
            raise IdentityUnavailable("Identity service unavailable") from None
