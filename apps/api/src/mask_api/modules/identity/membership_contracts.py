"""Trusted membership-administration values."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from mask_api.modules.identity.domain import Role


class MembershipValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class ReplaceMemberRoles(MembershipValue):
    session_token: SecretStr
    csrf_token: SecretStr
    target_user_id: UUID
    roles: frozenset[Role] = Field(min_length=1, max_length=len(Role))
    reason: str = Field(min_length=3, max_length=500)
    correlation_id: UUID

    @model_validator(mode="after")
    def validate_reason(self) -> "ReplaceMemberRoles":
        if self.reason != self.reason.strip():
            raise ValueError("Role-change reason must be trimmed")
        return self


class MemberRolesChanged(MembershipValue):
    organization_id: UUID
    target_user_id: UUID
    previous_roles: frozenset[Role]
    roles: frozenset[Role]
