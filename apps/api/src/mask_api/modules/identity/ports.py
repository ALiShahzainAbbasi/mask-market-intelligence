from typing import Protocol
from uuid import UUID

from pydantic import SecretStr

from mask_api.modules.identity.contracts import Membership, SessionRecord


class SessionReader(Protocol):
    def resolve(self, token: SecretStr) -> SessionRecord | None:
        """Lookup an opaque server session; unknown/revoked tokens grant nothing.

        The future adapter must never decode caller-supplied IDs/email/roles as
        identity, or treat the infrastructure smoke token as a user session.
        No production adapter exists until OIDC and session storage are ready.
        """
        ...


class MembershipReader(Protocol):
    def get(self, organization_id: UUID, user_id: UUID) -> Membership | None:
        """Read current membership/status/roles with both IDs scoped in SQL."""
        ...
