from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from pydantic import SecretStr

from mask_api.modules.identity.auth_contracts import (
    BootstrapOwnerRequest,
    BootstrapResult,
    CredentialRecord,
    IdentitySecurityEvent,
    NewSession,
    StoredSession,
)


class PasswordManager(Protocol):
    def hash(self, password: SecretStr) -> str: ...

    def verify(self, password_hash: str | None, password: SecretStr) -> bool: ...

    def needs_rehash(self, password_hash: str) -> bool: ...


class TokenManager(Protocol):
    def issue(self) -> tuple[SecretStr, str]: ...

    def digest(self, token: SecretStr) -> str: ...

    def matches(self, token: SecretStr, expected_digest: str) -> bool: ...


class AuthenticationStore(Protocol):
    def find(self, organization_id: UUID, normalized_email: str) -> CredentialRecord | None: ...

    def record_failed_login(
        self,
        credential: CredentialRecord | None,
        *,
        occurred_at: datetime,
        failure_limit: int,
        lockout: timedelta,
        event: IdentitySecurityEvent,
    ) -> None: ...

    def establish_session(
        self,
        credential: CredentialRecord,
        session: NewSession,
        *,
        occurred_at: datetime,
        replacement_hash: str | None,
        event: IdentitySecurityEvent,
    ) -> StoredSession | None: ...

    def resolve_hash(self, token_hash: str) -> StoredSession | None: ...

    def revoke(
        self,
        session_id: UUID,
        *,
        revoked_at: datetime,
        reason: str,
        event: IdentitySecurityEvent,
    ) -> bool: ...

    def rotate(
        self,
        current_session_id: UUID,
        replacement: NewSession,
        *,
        revoked_at: datetime,
        event: IdentitySecurityEvent,
    ) -> StoredSession | None: ...


class OwnerBootstrapStore(Protocol):
    def create_owner(
        self, request: BootstrapOwnerRequest, password_hash: str, *, created_at: datetime
    ) -> BootstrapResult: ...
