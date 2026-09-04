"""Internal trusted-boundary values, never request-body authentication schemas."""

from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, model_validator

from mask_api.modules.identity.domain import OrganizationStatus, Permission, Role, UserStatus


class IdentityValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class SessionRecord(IdentityValue):
    """Server-side lookup result. Contains no bearer token, email, or cached roles."""

    session_id: UUID
    organization_id: UUID
    user_id: UUID
    authenticated_at: AwareDatetime
    created_at: AwareDatetime
    expires_at: AwareDatetime
    revoked_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def ordered_times(self) -> "SessionRecord":
        if not self.authenticated_at <= self.created_at < self.expires_at:
            raise ValueError("Invalid session timeline")
        return self


class Membership(IdentityValue):
    organization_id: UUID
    user_id: UUID
    organization_status: OrganizationStatus
    user_status: UserStatus
    roles: frozenset[Role]


class AuthenticatedActor(IdentityValue):
    """Request-local context produced by IdentityService, not proof by itself."""

    organization_id: UUID
    user_id: UUID
    session_id: UUID
    authenticated_at: AwareDatetime
    roles: frozenset[Role]


class AccessGrant(IdentityValue):
    """Role gate only: resource scope, workflow rules, and audit still apply."""

    actor: AuthenticatedActor
    permission: Permission
    acting_role: Role
