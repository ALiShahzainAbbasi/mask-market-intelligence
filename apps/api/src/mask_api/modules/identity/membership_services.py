from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from mask_api.modules.identity.auth_ports import SessionMutationGuard
from mask_api.modules.identity.domain import Permission, Role
from mask_api.modules.identity.errors import IdentityUnavailable
from mask_api.modules.identity.membership_contracts import MemberRolesChanged, ReplaceMemberRoles
from mask_api.modules.identity.membership_ports import MembershipRoleStore
from mask_api.modules.identity.services import IdentityService


@dataclass(frozen=True)
class MembershipAdministrationService:
    identity: IdentityService
    csrf: SessionMutationGuard
    store: MembershipRoleStore
    clock: Callable[[], datetime]

    def replace_roles(self, request: ReplaceMemberRoles) -> MemberRolesChanged:
        self.csrf.validate_csrf(request.session_token, request.csrf_token)
        grant = self.identity.authorize_current_tenant(
            request.session_token,
            permission=Permission.MEMBERSHIP_MANAGE,
            acting_role=Role.ADMIN,
        )
        try:
            occurred_at = self.clock()
            if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
                raise ValueError("Clock must be timezone-aware")
        except Exception:
            raise IdentityUnavailable("Identity service unavailable") from None
        return self.store.replace_roles(
            organization_id=grant.actor.organization_id,
            actor_user_id=grant.actor.user_id,
            actor_session_id=grant.actor.session_id,
            target_user_id=request.target_user_id,
            roles=request.roles,
            reason=request.reason,
            correlation_id=request.correlation_id,
            occurred_at=occurred_at,
        )
