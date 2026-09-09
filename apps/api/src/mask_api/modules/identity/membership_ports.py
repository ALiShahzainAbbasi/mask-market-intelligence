from datetime import datetime
from typing import Protocol
from uuid import UUID

from mask_api.modules.identity.domain import Role
from mask_api.modules.identity.membership_contracts import MemberRolesChanged


class MembershipRoleStore(Protocol):
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
    ) -> MemberRolesChanged: ...
