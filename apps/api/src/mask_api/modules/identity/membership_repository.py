"""Transactional, tenant-scoped membership role administration."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from mask_api.modules.identity.auth_models import IdentitySecurityEvent
from mask_api.modules.identity.domain import (
    IdentityEventOutcome,
    IdentityEventType,
    Role,
    UserStatus,
)
from mask_api.modules.identity.errors import (
    IdentityUnavailable,
    LastAdministratorRequired,
    MembershipNotFound,
)
from mask_api.modules.identity.membership_contracts import MemberRolesChanged
from mask_api.modules.identity.models import User, UserRole


class SQLAlchemyMembershipRoleStore:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self.sessions = sessions

    def replace_roles(
        self,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        actor_session_id: UUID,
        target_user_id: UUID,
        roles: frozenset[Role],
        reason: str,
        correlation_id: UUID,
        occurred_at: datetime,
    ) -> MemberRolesChanged:
        try:
            with self.sessions.begin() as session:
                target_status = session.scalar(
                    select(User.status)
                    .where(User.organization_id == organization_id, User.id == target_user_id)
                    .with_for_update()
                )
                if target_status is None:
                    raise MembershipNotFound("Member not found")
                previous = frozenset(
                    session.scalars(
                        select(UserRole.role)
                        .where(
                            UserRole.organization_id == organization_id,
                            UserRole.user_id == target_user_id,
                        )
                        .with_for_update()
                    ).all()
                )
                if previous == roles:
                    return MemberRolesChanged(
                        organization_id=organization_id,
                        target_user_id=target_user_id,
                        previous_roles=previous,
                        roles=roles,
                    )
                if Role.ADMIN in previous and Role.ADMIN not in roles:
                    active_other_admins = session.scalar(
                        select(func.count())
                        .select_from(UserRole)
                        .join(
                            User,
                            (User.organization_id == UserRole.organization_id)
                            & (User.id == UserRole.user_id),
                        )
                        .where(
                            UserRole.organization_id == organization_id,
                            UserRole.role == Role.ADMIN,
                            User.status == UserStatus.ACTIVE,
                            UserRole.user_id != target_user_id,
                        )
                    )
                    if not active_other_admins:
                        raise LastAdministratorRequired("An active administrator is required")
                session.execute(
                    delete(UserRole).where(
                        UserRole.organization_id == organization_id,
                        UserRole.user_id == target_user_id,
                    )
                )
                session.add_all(
                    UserRole(
                        id=uuid4(),
                        organization_id=organization_id,
                        user_id=target_user_id,
                        role=role,
                        created_at=occurred_at,
                    )
                    for role in sorted(roles, key=lambda value: value.value)
                )
                session.add(
                    IdentitySecurityEvent(
                        id=uuid4(),
                        event_type=IdentityEventType.ROLES_CHANGED,
                        outcome=IdentityEventOutcome.SUCCEEDED,
                        organization_id=organization_id,
                        user_id=actor_user_id,
                        subject_user_id=target_user_id,
                        session_id=actor_session_id,
                        correlation_id=correlation_id,
                        reason_code="membership_roles_replaced",
                        details_json={
                            "previous_roles": sorted(value.value for value in previous),
                            "new_roles": sorted(value.value for value in roles),
                            "reason": reason,
                        },
                        occurred_at=occurred_at,
                    )
                )
            return MemberRolesChanged(
                organization_id=organization_id,
                target_user_id=target_user_id,
                previous_roles=previous,
                roles=roles,
            )
        except (MembershipNotFound, LastAdministratorRequired):
            raise
        except (SQLAlchemyError, ValueError):
            raise IdentityUnavailable("Identity service unavailable") from None
