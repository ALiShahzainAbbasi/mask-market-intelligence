from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from pydantic import SecretStr

from mask_api.modules.identity.auth_contracts import (
    BootstrapOwnerRequest,
    BootstrapResult,
    CredentialRecord,
    IdentitySecurityEvent,
    IssuedSession,
    LoginRequest,
    NewSession,
    StoredSession,
)
from mask_api.modules.identity.auth_ports import (
    AuthenticationStore,
    OwnerBootstrapStore,
    PasswordManager,
    TokenManager,
)
from mask_api.modules.identity.contracts import SessionRecord
from mask_api.modules.identity.domain import (
    IdentityEventOutcome,
    IdentityEventType,
    OrganizationStatus,
    UserStatus,
    normalize_email,
)
from mask_api.modules.identity.errors import (
    AuthenticationRequired,
    BootstrapAlreadyCompleted,
    IdentityUnavailable,
    InvalidCredentials,
    InvalidCsrfToken,
    LoginRateLimited,
    PasswordPolicyViolation,
)


def _safe_now(clock: Callable[[], datetime]) -> datetime:
    try:
        now = clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Clock must be timezone-aware")
        return now
    except Exception:
        raise IdentityUnavailable("Identity service unavailable") from None


def _validate_new_password(password: SecretStr, normalized_email: str) -> None:
    value = password.get_secret_value()
    if not 12 <= len(value) <= 128 or not value.strip() or value.lower() == normalized_email:
        raise PasswordPolicyViolation("Password does not meet policy")


@dataclass(frozen=True)
class LocalAuthenticationService:
    store: AuthenticationStore
    passwords: PasswordManager
    tokens: TokenManager
    clock: Callable[[], datetime]
    session_lifetime: timedelta
    failure_limit: int
    lockout: timedelta

    def __post_init__(self) -> None:
        if not timedelta(minutes=5) <= self.session_lifetime <= timedelta(days=7):
            raise ValueError("Session lifetime is outside the allowed range")
        if not 3 <= self.failure_limit <= 10:
            raise ValueError("Login failure limit is outside the allowed range")
        if not timedelta(seconds=30) <= self.lockout <= timedelta(hours=24):
            raise ValueError("Login lockout is outside the allowed range")

    def login(self, request: LoginRequest) -> IssuedSession:
        now = _safe_now(self.clock)
        try:
            email = normalize_email(request.email)
            credential = self.store.find(request.organization_id, email)
        except ValueError:
            try:
                self.passwords.verify(None, request.password)
            except Exception:
                raise IdentityUnavailable("Identity service unavailable") from None
            self._record_failure(
                None,
                request,
                now,
                event_type=IdentityEventType.LOGIN_FAILED,
                reason="invalid_credentials",
            )
            raise InvalidCredentials("Invalid credentials") from None
        except Exception:
            raise IdentityUnavailable("Identity service unavailable") from None

        try:
            password_valid = self.passwords.verify(
                credential.password_hash if credential is not None else None,
                request.password,
            )
        except Exception:
            raise IdentityUnavailable("Identity service unavailable") from None
        locked = credential is not None and (
            credential.locked_until is not None and now < credential.locked_until
        )
        if locked:
            self._record_failure(
                credential,
                request,
                now,
                event_type=IdentityEventType.LOGIN_THROTTLED,
                reason="account_locked",
            )
            raise LoginRateLimited("Login temporarily unavailable")

        active = credential is not None and (
            credential.organization_status == OrganizationStatus.ACTIVE
            and credential.user_status == UserStatus.ACTIVE
        )
        if not password_valid or not active:
            self._record_failure(
                credential,
                request,
                now,
                event_type=IdentityEventType.LOGIN_FAILED,
                reason="invalid_credentials",
            )
            raise InvalidCredentials("Invalid credentials")

        assert credential is not None
        session_token, token_hash = self.tokens.issue()
        csrf_token, csrf_hash = self.tokens.issue()
        session_id = uuid4()
        new_session = NewSession(
            session_id=session_id,
            organization_id=credential.organization_id,
            user_id=credential.user_id,
            token_hash=token_hash,
            csrf_hash=csrf_hash,
            authenticated_at=now,
            created_at=now,
            expires_at=now + self.session_lifetime,
        )
        try:
            replacement_hash = (
                self.passwords.hash(request.password)
                if self.passwords.needs_rehash(credential.password_hash)
                else None
            )
        except Exception:
            raise IdentityUnavailable("Identity service unavailable") from None
        event = self._event(
            IdentityEventType.LOGIN_SUCCEEDED,
            IdentityEventOutcome.SUCCEEDED,
            request.correlation_id,
            now,
            reason="credentials_verified",
            credential=credential,
            session_id=session_id,
        )
        try:
            stored = self.store.establish_session(
                credential,
                new_session,
                occurred_at=now,
                replacement_hash=replacement_hash,
                event=event,
            )
        except Exception:
            raise IdentityUnavailable("Identity service unavailable") from None
        if stored is None:
            raise InvalidCredentials("Invalid credentials")
        return IssuedSession(
            record=stored.record,
            session_token=session_token,
            csrf_token=csrf_token,
        )

    def logout(
        self,
        session_token: SecretStr,
        csrf_token: SecretStr,
        *,
        correlation_id: UUID,
    ) -> None:
        now = _safe_now(self.clock)
        stored = self._live_session(session_token, now)
        if len(csrf_token.get_secret_value()) > 4096 or not self.tokens.matches(
            csrf_token, stored.csrf_hash
        ):
            raise InvalidCsrfToken("CSRF validation failed")
        event = self._event(
            IdentityEventType.SESSION_REVOKED,
            IdentityEventOutcome.SUCCEEDED,
            correlation_id,
            now,
            reason="logout",
            record=stored.record,
        )
        try:
            revoked = self.store.revoke(
                stored.record.session_id,
                revoked_at=now,
                reason="logout",
                event=event,
            )
        except Exception:
            raise IdentityUnavailable("Identity service unavailable") from None
        if not revoked:
            raise AuthenticationRequired("Authentication required")

    def rotate(
        self,
        session_token: SecretStr,
        csrf_token: SecretStr,
        *,
        correlation_id: UUID,
    ) -> IssuedSession:
        now = _safe_now(self.clock)
        current = self._live_session(session_token, now)
        if len(csrf_token.get_secret_value()) > 4096 or not self.tokens.matches(
            csrf_token, current.csrf_hash
        ):
            raise InvalidCsrfToken("CSRF validation failed")
        replacement_token, replacement_hash = self.tokens.issue()
        replacement_csrf, replacement_csrf_hash = self.tokens.issue()
        replacement_id = uuid4()
        replacement = NewSession(
            session_id=replacement_id,
            organization_id=current.record.organization_id,
            user_id=current.record.user_id,
            token_hash=replacement_hash,
            csrf_hash=replacement_csrf_hash,
            authenticated_at=current.record.authenticated_at,
            created_at=now,
            expires_at=current.record.expires_at,
            rotated_from_id=current.record.session_id,
        )
        event = self._event(
            IdentityEventType.SESSION_ROTATED,
            IdentityEventOutcome.SUCCEEDED,
            correlation_id,
            now,
            reason="token_rotation",
            record=current.record,
            session_id=replacement_id,
        )
        try:
            stored = self.store.rotate(
                current.record.session_id,
                replacement,
                revoked_at=now,
                event=event,
            )
        except Exception:
            raise IdentityUnavailable("Identity service unavailable") from None
        if stored is None:
            raise AuthenticationRequired("Authentication required")
        return IssuedSession(
            record=stored.record,
            session_token=replacement_token,
            csrf_token=replacement_csrf,
        )

    def _live_session(self, token: SecretStr, now: datetime) -> StoredSession:
        if not token.get_secret_value() or len(token.get_secret_value()) > 4096:
            raise AuthenticationRequired("Authentication required")
        try:
            stored = self.store.resolve_hash(self.tokens.digest(token))
        except Exception:
            raise IdentityUnavailable("Identity service unavailable") from None
        if (
            stored is None
            or stored.record.revoked_at is not None
            or not stored.record.created_at <= now < stored.record.expires_at
        ):
            raise AuthenticationRequired("Authentication required")
        return stored

    def _record_failure(
        self,
        credential: CredentialRecord | None,
        request: LoginRequest,
        now: datetime,
        *,
        event_type: IdentityEventType,
        reason: str,
    ) -> None:
        event = self._event(
            event_type,
            IdentityEventOutcome.DENIED,
            request.correlation_id,
            now,
            reason=reason,
            credential=credential,
        )
        try:
            self.store.record_failed_login(
                credential,
                occurred_at=now,
                failure_limit=self.failure_limit,
                lockout=self.lockout,
                event=event,
            )
        except Exception:
            raise IdentityUnavailable("Identity service unavailable") from None

    @staticmethod
    def _event(
        event_type: IdentityEventType,
        outcome: IdentityEventOutcome,
        correlation_id: UUID,
        occurred_at: datetime,
        *,
        reason: str,
        credential: CredentialRecord | None = None,
        record: SessionRecord | None = None,
        session_id: UUID | None = None,
    ) -> IdentitySecurityEvent:
        return IdentitySecurityEvent(
            event_type=event_type,
            outcome=outcome,
            correlation_id=correlation_id,
            occurred_at=occurred_at,
            organization_id=(
                credential.organization_id
                if credential is not None
                else record.organization_id
                if record is not None
                else None
            ),
            user_id=(
                credential.user_id
                if credential is not None
                else record.user_id
                if record is not None
                else None
            ),
            session_id=session_id or (record.session_id if record is not None else None),
            reason_code=reason,
        )


@dataclass(frozen=True)
class OwnerBootstrapService:
    store: OwnerBootstrapStore
    passwords: PasswordManager
    clock: Callable[[], datetime]

    def create_owner(self, request: BootstrapOwnerRequest) -> BootstrapResult:
        now = _safe_now(self.clock)
        try:
            email = normalize_email(request.email)
        except ValueError as error:
            raise PasswordPolicyViolation("Invalid owner details") from error
        _validate_new_password(request.password, email)
        if not request.organization_name.strip() or not request.owner_name.strip():
            raise PasswordPolicyViolation("Invalid owner details")
        normalized = request.model_copy(
            update={
                "organization_name": request.organization_name.strip(),
                "owner_name": request.owner_name.strip(),
                "email": email,
            }
        )
        try:
            password_hash = self.passwords.hash(request.password)
        except Exception:
            raise IdentityUnavailable("Identity service unavailable") from None
        try:
            return self.store.create_owner(normalized, password_hash, created_at=now)
        except Exception as error:
            if isinstance(error, BootstrapAlreadyCompleted):
                raise
            raise IdentityUnavailable("Identity service unavailable") from None
