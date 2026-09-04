from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from mask_api.modules.identity.auth_contracts import (
    BootstrapOwnerRequest,
    BootstrapResult,
    CredentialRecord,
    IdentitySecurityEvent,
    LoginRequest,
    NewSession,
    StoredSession,
)
from mask_api.modules.identity.auth_services import (
    LocalAuthenticationService,
    OwnerBootstrapService,
)
from mask_api.modules.identity.contracts import SessionRecord
from mask_api.modules.identity.domain import (
    IdentityEventType,
    OrganizationStatus,
    UserStatus,
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
from mask_api.modules.identity.security import Sha256TokenManager
from mask_api.modules.identity.session_adapter import HashedSessionReader
from pydantic import SecretStr

NOW = datetime(2026, 9, 3, 18, 30, tzinfo=UTC)
ORG_ID = UUID("10000000-0000-0000-0000-000000000001")
USER_ID = UUID("20000000-0000-0000-0000-000000000002")
CORRELATION_ID = UUID("30000000-0000-0000-0000-000000000003")


class FakePasswords:
    def __init__(self, *, valid: bool = True, rehash: bool = False) -> None:
        self.valid = valid
        self.rehash = rehash
        self.verify_hashes: list[str | None] = []
        self.hashed: list[str] = []

    def hash(self, password: SecretStr) -> str:
        self.hashed.append(password.get_secret_value())
        return "$argon2id$replacement-hash-value"

    def verify(self, password_hash: str | None, password: SecretStr) -> bool:
        self.verify_hashes.append(password_hash)
        return self.valid and password_hash is not None

    def needs_rehash(self, password_hash: str) -> bool:
        return self.rehash


class FakeAuthenticationStore:
    def __init__(self, credential: CredentialRecord | None) -> None:
        self.credential = credential
        self.failures: list[IdentitySecurityEvent] = []
        self.established: list[NewSession] = []
        self.replacements: list[str | None] = []
        self.resolved: dict[str, StoredSession] = {}
        self.revocations: list[tuple[UUID, str]] = []
        self.rotations: list[NewSession] = []
        self.establish_result = True
        self.revoke_result = True
        self.rotate_result = True
        self.error: Exception | None = None

    def find(self, organization_id: UUID, normalized_email: str) -> CredentialRecord | None:
        self._raise()
        assert organization_id == ORG_ID
        assert normalized_email == "owner@example.com"
        return self.credential

    def record_failed_login(
        self,
        credential: CredentialRecord | None,
        *,
        occurred_at: datetime,
        failure_limit: int,
        lockout: timedelta,
        event: IdentitySecurityEvent,
    ) -> None:
        self._raise()
        assert occurred_at == NOW
        assert failure_limit == 5
        assert lockout == timedelta(minutes=15)
        self.failures.append(event)

    def establish_session(
        self,
        credential: CredentialRecord,
        session: NewSession,
        *,
        occurred_at: datetime,
        replacement_hash: str | None,
        event: IdentitySecurityEvent,
    ) -> StoredSession | None:
        self._raise()
        self.established.append(session)
        self.replacements.append(replacement_hash)
        if not self.establish_result:
            return None
        return stored_from_new(session)

    def resolve_hash(self, token_hash: str) -> StoredSession | None:
        self._raise()
        return self.resolved.get(token_hash)

    def revoke(
        self,
        session_id: UUID,
        *,
        revoked_at: datetime,
        reason: str,
        event: IdentitySecurityEvent,
    ) -> bool:
        self._raise()
        self.revocations.append((session_id, reason))
        return self.revoke_result

    def rotate(
        self,
        current_session_id: UUID,
        replacement: NewSession,
        *,
        revoked_at: datetime,
        event: IdentitySecurityEvent,
    ) -> StoredSession | None:
        self._raise()
        self.rotations.append(replacement)
        return stored_from_new(replacement) if self.rotate_result else None

    def _raise(self) -> None:
        if self.error is not None:
            raise self.error


class FakeBootstrapStore:
    def __init__(self) -> None:
        self.requests: list[BootstrapOwnerRequest] = []
        self.hashes: list[str] = []
        self.error: Exception | None = None

    def create_owner(
        self,
        request: BootstrapOwnerRequest,
        password_hash: str,
        *,
        created_at: datetime,
    ) -> BootstrapResult:
        if self.error is not None:
            raise self.error
        self.requests.append(request)
        self.hashes.append(password_hash)
        return BootstrapResult(organization_id=ORG_ID, user_id=USER_ID, created_at=created_at)


def credential(**updates: object) -> CredentialRecord:
    values: dict[str, object] = {
        "organization_id": ORG_ID,
        "user_id": USER_ID,
        "password_hash": "$argon2id$existing-password-hash",
        "organization_status": OrganizationStatus.ACTIVE,
        "user_status": UserStatus.ACTIVE,
        "failed_login_count": 0,
    }
    values.update(updates)
    return CredentialRecord.model_validate(values)


def stored_from_new(value: NewSession) -> StoredSession:
    return StoredSession(
        record=SessionRecord(
            session_id=value.session_id,
            organization_id=value.organization_id,
            user_id=value.user_id,
            authenticated_at=value.authenticated_at,
            created_at=value.created_at,
            expires_at=value.expires_at,
        ),
        csrf_hash=value.csrf_hash,
    )


def stored_session(
    *, expires_at: datetime | None = None, revoked_at: datetime | None = None
) -> StoredSession:
    csrf = SecretStr("csrf-token")
    tokens = Sha256TokenManager()
    return StoredSession(
        record=SessionRecord(
            session_id=uuid4(),
            organization_id=ORG_ID,
            user_id=USER_ID,
            authenticated_at=NOW - timedelta(minutes=1),
            created_at=NOW - timedelta(minutes=1),
            expires_at=expires_at or NOW + timedelta(hours=1),
            revoked_at=revoked_at,
        ),
        csrf_hash=tokens.digest(csrf),
    )


def request(*, email: str = "owner@example.com") -> LoginRequest:
    return LoginRequest(
        organization_id=ORG_ID,
        email=email,
        password=SecretStr("correct horse battery staple"),
        correlation_id=CORRELATION_ID,
    )


def service(
    store: FakeAuthenticationStore,
    passwords: FakePasswords | None = None,
) -> LocalAuthenticationService:
    return LocalAuthenticationService(
        store=store,
        passwords=passwords or FakePasswords(),
        tokens=Sha256TokenManager(),
        clock=lambda: NOW,
        session_lifetime=timedelta(hours=8),
        failure_limit=5,
        lockout=timedelta(minutes=15),
    )


def test_login_creates_hashed_session_and_rehashes_atomically() -> None:
    store = FakeAuthenticationStore(credential())
    passwords = FakePasswords(rehash=True)

    issued = service(store, passwords).login(request())

    persisted = store.established[0]
    assert issued.record.session_id == persisted.session_id
    assert issued.record.expires_at == NOW + timedelta(hours=8)
    assert persisted.token_hash == Sha256TokenManager().digest(issued.session_token)
    assert persisted.csrf_hash == Sha256TokenManager().digest(issued.csrf_token)
    assert issued.session_token.get_secret_value() not in persisted.token_hash
    assert store.replacements == ["$argon2id$replacement-hash-value"]
    assert passwords.hashed == ["correct horse battery staple"]


@pytest.mark.parametrize(
    ("stored_credential", "email", "password_valid", "event_type", "error"),
    [
        (None, "owner@example.com", False, IdentityEventType.LOGIN_FAILED, InvalidCredentials),
        (
            credential(user_status=UserStatus.SUSPENDED),
            "owner@example.com",
            True,
            IdentityEventType.LOGIN_FAILED,
            InvalidCredentials,
        ),
        (
            credential(locked_until=NOW + timedelta(minutes=1)),
            "owner@example.com",
            True,
            IdentityEventType.LOGIN_THROTTLED,
            LoginRateLimited,
        ),
        (None, "invalid email", False, IdentityEventType.LOGIN_FAILED, InvalidCredentials),
    ],
)
def test_login_denials_are_generic_audited_and_issue_no_session(
    stored_credential: CredentialRecord | None,
    email: str,
    password_valid: bool,
    event_type: IdentityEventType,
    error: type[Exception],
) -> None:
    store = FakeAuthenticationStore(stored_credential)
    passwords = FakePasswords(valid=password_valid)

    with pytest.raises(error):
        service(store, passwords).login(request(email=email))

    assert store.established == []
    assert store.failures[0].event_type == event_type
    assert store.failures[0].reason_code in {"invalid_credentials", "account_locked"}
    if stored_credential is None:
        assert store.failures[0].user_id is None


def test_login_denies_when_account_changes_after_password_verification() -> None:
    store = FakeAuthenticationStore(credential())
    store.establish_result = False
    with pytest.raises(InvalidCredentials):
        service(store).login(request())


def test_login_dependency_failures_are_sanitized() -> None:
    store = FakeAuthenticationStore(credential())
    store.error = RuntimeError("database password leaked")
    with pytest.raises(IdentityUnavailable, match="Identity service unavailable") as caught:
        service(store).login(request())
    assert "database password" not in str(caught.value)


def test_logout_requires_live_session_and_matching_csrf() -> None:
    tokens = Sha256TokenManager()
    raw_session = SecretStr("session-token")
    current = stored_session()
    store = FakeAuthenticationStore(credential())
    store.resolved[tokens.digest(raw_session)] = current
    authentication = service(store)

    with pytest.raises(InvalidCsrfToken):
        authentication.logout(
            raw_session,
            SecretStr("wrong-csrf"),
            correlation_id=CORRELATION_ID,
        )
    assert store.revocations == []

    authentication.logout(
        raw_session,
        SecretStr("csrf-token"),
        correlation_id=CORRELATION_ID,
    )
    assert store.revocations == [(current.record.session_id, "logout")]


@pytest.mark.parametrize(
    "current",
    [stored_session(expires_at=NOW), stored_session(revoked_at=NOW - timedelta(seconds=1))],
)
def test_logout_rejects_expired_or_revoked_session(current: StoredSession) -> None:
    tokens = Sha256TokenManager()
    raw_session = SecretStr("session-token")
    store = FakeAuthenticationStore(credential())
    store.resolved[tokens.digest(raw_session)] = current
    with pytest.raises(AuthenticationRequired):
        service(store).logout(
            raw_session,
            SecretStr("csrf-token"),
            correlation_id=CORRELATION_ID,
        )


def test_rotation_changes_both_secrets_without_extending_absolute_expiry() -> None:
    tokens = Sha256TokenManager()
    raw_session = SecretStr("session-token")
    current = stored_session()
    store = FakeAuthenticationStore(credential())
    store.resolved[tokens.digest(raw_session)] = current

    issued = service(store).rotate(
        raw_session,
        SecretStr("csrf-token"),
        correlation_id=CORRELATION_ID,
    )

    replacement = store.rotations[0]
    assert replacement.rotated_from_id == current.record.session_id
    assert replacement.authenticated_at == current.record.authenticated_at
    assert replacement.expires_at == current.record.expires_at
    assert issued.session_token.get_secret_value() != raw_session.get_secret_value()
    assert issued.csrf_token.get_secret_value() != "csrf-token"


def test_hashed_session_reader_never_decodes_identity_from_token() -> None:
    tokens = Sha256TokenManager()
    raw_session = SecretStr("opaque-session-token")
    current = stored_session()
    store = FakeAuthenticationStore(credential())
    store.resolved[tokens.digest(raw_session)] = current

    reader = HashedSessionReader(store=store, tokens=tokens)
    assert reader.resolve(raw_session) == current.record
    assert reader.resolve(SecretStr("unknown")) is None


@pytest.mark.parametrize(
    "arguments",
    [
        {"session_lifetime": timedelta(minutes=1)},
        {"session_lifetime": timedelta(days=8)},
        {"failure_limit": 2},
        {"failure_limit": 11},
        {"lockout": timedelta(seconds=1)},
        {"lockout": timedelta(days=2)},
    ],
)
def test_authentication_configuration_is_bounded(arguments: dict[str, object]) -> None:
    values: dict[str, object] = {
        "store": FakeAuthenticationStore(credential()),
        "passwords": FakePasswords(),
        "tokens": Sha256TokenManager(),
        "clock": lambda: NOW,
        "session_lifetime": timedelta(hours=8),
        "failure_limit": 5,
        "lockout": timedelta(minutes=15),
    }
    values.update(arguments)
    with pytest.raises(ValueError):
        LocalAuthenticationService(**values)  # type: ignore[arg-type]


def test_owner_bootstrap_normalizes_input_and_hashes_password() -> None:
    store = FakeBootstrapStore()
    passwords = FakePasswords()
    bootstrap = OwnerBootstrapService(store=store, passwords=passwords, clock=lambda: NOW)
    result = bootstrap.create_owner(
        BootstrapOwnerRequest(
            organization_name="  MASK AI  ",
            owner_name="  Owner  ",
            email=" Owner@Example.COM ",
            password=SecretStr("correct horse battery staple"),
            correlation_id=CORRELATION_ID,
        )
    )

    assert result.organization_id == ORG_ID
    assert store.requests[0].organization_name == "MASK AI"
    assert store.requests[0].owner_name == "Owner"
    assert store.requests[0].email == "owner@example.com"
    assert store.hashes == ["$argon2id$replacement-hash-value"]


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("not-an-email", "correct horse battery staple"),
        ("owner@example.com", "too-short"),
        ("owner@example.com", "owner@example.com"),
    ],
)
def test_owner_bootstrap_rejects_invalid_credentials(email: str, password: str) -> None:
    bootstrap = OwnerBootstrapService(
        store=FakeBootstrapStore(), passwords=FakePasswords(), clock=lambda: NOW
    )
    with pytest.raises((PasswordPolicyViolation, ValueError)):
        bootstrap.create_owner(
            BootstrapOwnerRequest(
                organization_name="MASK AI",
                owner_name="Owner",
                email=email,
                password=SecretStr(password),
                correlation_id=CORRELATION_ID,
            )
        )


def test_owner_bootstrap_preserves_one_time_conflict() -> None:
    store = FakeBootstrapStore()
    store.error = BootstrapAlreadyCompleted("already complete")
    bootstrap = OwnerBootstrapService(store=store, passwords=FakePasswords(), clock=lambda: NOW)
    with pytest.raises(BootstrapAlreadyCompleted):
        bootstrap.create_owner(
            BootstrapOwnerRequest(
                organization_name="MASK AI",
                owner_name="Owner",
                email="owner@example.com",
                password=SecretStr("correct horse battery staple"),
                correlation_id=CORRELATION_ID,
            )
        )
