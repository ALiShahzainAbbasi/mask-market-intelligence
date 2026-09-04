"""Authentication values. Raw secrets never belong in logs or persistence."""

from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, SecretStr, model_validator

from mask_api.modules.identity.contracts import SessionRecord
from mask_api.modules.identity.domain import (
    IdentityEventOutcome,
    IdentityEventType,
    OrganizationStatus,
    UserStatus,
)


class AuthValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class LoginRequest(AuthValue):
    organization_id: UUID
    email: str = Field(min_length=4, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=256)
    correlation_id: UUID


class CredentialRecord(AuthValue):
    organization_id: UUID
    user_id: UUID
    password_hash: str = Field(min_length=20, max_length=1000)
    organization_status: OrganizationStatus
    user_status: UserStatus
    failed_login_count: int = Field(ge=0)
    locked_until: AwareDatetime | None = None


class NewSession(AuthValue):
    session_id: UUID
    organization_id: UUID
    user_id: UUID
    token_hash: str = Field(min_length=64, max_length=64)
    csrf_hash: str = Field(min_length=64, max_length=64)
    authenticated_at: AwareDatetime
    created_at: AwareDatetime
    expires_at: AwareDatetime
    rotated_from_id: UUID | None = None

    @model_validator(mode="after")
    def ordered_times(self) -> "NewSession":
        if not self.authenticated_at <= self.created_at < self.expires_at:
            raise ValueError("Invalid session timeline")
        return self


class StoredSession(AuthValue):
    record: SessionRecord
    csrf_hash: str = Field(min_length=64, max_length=64)


class IssuedSession(AuthValue):
    record: SessionRecord
    session_token: SecretStr
    csrf_token: SecretStr


class IdentitySecurityEvent(AuthValue):
    event_type: IdentityEventType
    outcome: IdentityEventOutcome
    correlation_id: UUID
    occurred_at: AwareDatetime
    organization_id: UUID | None = None
    user_id: UUID | None = None
    session_id: UUID | None = None
    reason_code: str = Field(min_length=1, max_length=64)


class BootstrapOwnerRequest(AuthValue):
    organization_name: str = Field(min_length=1, max_length=200)
    owner_name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=4, max_length=254)
    password: SecretStr = Field(min_length=12, max_length=128)
    correlation_id: UUID


class BootstrapResult(AuthValue):
    organization_id: UUID
    user_id: UUID
    created_at: AwareDatetime
