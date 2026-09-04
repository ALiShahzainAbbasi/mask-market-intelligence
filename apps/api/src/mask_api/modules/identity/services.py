from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from pydantic import SecretStr

from mask_api.modules.identity.contracts import AccessGrant, AuthenticatedActor, SessionRecord
from mask_api.modules.identity.domain import (
    RECENT_AUTH_PERMISSIONS,
    OrganizationStatus,
    Permission,
    Role,
    UserStatus,
    role_permits,
)
from mask_api.modules.identity.errors import (
    AccessDenied,
    AuthenticationRequired,
    IdentityUnavailable,
    RecentAuthenticationRequired,
)
from mask_api.modules.identity.ports import MembershipReader, SessionReader


@dataclass(frozen=True)
class IdentityService:
    sessions: SessionReader
    memberships: MembershipReader
    clock: Callable[[], datetime]
    recent_auth_max_age: timedelta

    def __post_init__(self) -> None:
        if self.recent_auth_max_age <= timedelta(0):
            raise ValueError("Recent-authentication window must be positive")

    def authenticate(self, token: SecretStr | None) -> AuthenticatedActor:
        if token is None or not token.get_secret_value() or len(token.get_secret_value()) > 4096:
            raise AuthenticationRequired("Authentication required")
        try:
            session = self.sessions.resolve(token)
        except Exception:
            raise IdentityUnavailable("Identity service unavailable") from None
        if session is None:
            raise AuthenticationRequired("Authentication required")
        self._require_live_session(session)
        try:
            membership = self.memberships.get(session.organization_id, session.user_id)
        except Exception:
            raise IdentityUnavailable("Identity service unavailable") from None
        # Include lookup latency in expiry enforcement. There is no stale-role cache.
        self._require_live_session(session)
        if (
            membership is None
            or membership.organization_id != session.organization_id
            or membership.user_id != session.user_id
            or membership.organization_status != OrganizationStatus.ACTIVE
            or membership.user_status != UserStatus.ACTIVE
            or not membership.roles
        ):
            raise AccessDenied("Access denied")
        return AuthenticatedActor(
            organization_id=session.organization_id,
            user_id=session.user_id,
            session_id=session.session_id,
            authenticated_at=session.authenticated_at,
            roles=membership.roles,
        )

    def authorize(
        self,
        token: SecretStr | None,
        *,
        organization_id: UUID,
        permission: Permission,
        acting_role: Role,
    ) -> AccessGrant:
        actor = self.authenticate(token)
        if actor.organization_id != organization_id or not role_permits(
            actor.roles, permission, acting_role
        ):
            raise AccessDenied("Access denied")
        if permission in RECENT_AUTH_PERMISSIONS:
            age = self._now() - actor.authenticated_at
            if not timedelta(0) <= age < self.recent_auth_max_age:
                raise RecentAuthenticationRequired("Recent authentication required")
        return AccessGrant(actor=actor, permission=permission, acting_role=acting_role)

    def _now(self) -> datetime:
        try:
            now = self.clock()
            if now.tzinfo is None or now.utcoffset() is None:
                raise ValueError("Clock must be timezone-aware")
            return now
        except Exception:
            raise IdentityUnavailable("Identity service unavailable") from None

    def _require_live_session(self, session: SessionRecord) -> None:
        now = self._now()
        if session.revoked_at is not None or not session.created_at <= now < session.expires_at:
            raise AuthenticationRequired("Authentication required")
