"""Transactional PostgreSQL adapters for local authentication use cases."""

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from mask_api.modules.identity.auth_contracts import (
    BootstrapOwnerRequest,
    BootstrapResult,
    CredentialRecord,
    NewSession,
    StoredSession,
)
from mask_api.modules.identity.auth_contracts import (
    IdentitySecurityEvent as SecurityEventValue,
)
from mask_api.modules.identity.auth_models import (
    IdentitySecurityEvent,
    ServerSession,
    UserCredential,
)
from mask_api.modules.identity.contracts import SessionRecord
from mask_api.modules.identity.domain import (
    IdentityEventOutcome,
    IdentityEventType,
    OrganizationStatus,
    Role,
    UserStatus,
)
from mask_api.modules.identity.errors import BootstrapAlreadyCompleted, IdentityUnavailable
from mask_api.modules.identity.models import Organization, User, UserRole

_BOOTSTRAP_ADVISORY_LOCK = 4_894_124_268_087_859_217


def _event_model(event: SecurityEventValue) -> IdentitySecurityEvent:
    return IdentitySecurityEvent(
        id=uuid4(),
        event_type=event.event_type,
        outcome=event.outcome,
        organization_id=event.organization_id,
        user_id=event.user_id,
        session_id=event.session_id,
        correlation_id=event.correlation_id,
        reason_code=event.reason_code,
        occurred_at=event.occurred_at,
    )


def _stored_session(record: ServerSession) -> StoredSession:
    return StoredSession(
        record=SessionRecord(
            session_id=record.id,
            organization_id=record.organization_id,
            user_id=record.user_id,
            authenticated_at=record.authenticated_at,
            created_at=record.created_at,
            expires_at=record.expires_at,
            revoked_at=record.revoked_at,
        ),
        csrf_hash=record.csrf_hash,
    )


def _new_session_model(value: NewSession) -> ServerSession:
    return ServerSession(
        id=value.session_id,
        organization_id=value.organization_id,
        user_id=value.user_id,
        token_hash=value.token_hash,
        csrf_hash=value.csrf_hash,
        authenticated_at=value.authenticated_at,
        created_at=value.created_at,
        expires_at=value.expires_at,
        rotated_from_id=value.rotated_from_id,
    )


class SQLAlchemyAuthenticationStore:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self.sessions = sessions

    def find(self, organization_id: UUID, normalized_email: str) -> CredentialRecord | None:
        statement = (
            select(UserCredential, Organization.status, User.status)
            .join(
                User,
                (User.organization_id == UserCredential.organization_id)
                & (User.id == UserCredential.user_id),
            )
            .join(Organization, Organization.id == User.organization_id)
            .where(
                UserCredential.organization_id == organization_id,
                User.email == normalized_email,
            )
        )
        try:
            with self.sessions() as session:
                row = session.execute(statement).one_or_none()
            if row is None:
                return None
            credential, organization_status, user_status = row
            return CredentialRecord(
                organization_id=credential.organization_id,
                user_id=credential.user_id,
                password_hash=credential.password_hash,
                organization_status=organization_status,
                user_status=user_status,
                failed_login_count=credential.failed_login_count,
                locked_until=credential.locked_until,
            )
        except (SQLAlchemyError, ValueError):
            raise IdentityUnavailable("Identity service unavailable") from None

    def record_failed_login(
        self,
        credential: CredentialRecord | None,
        *,
        occurred_at: datetime,
        failure_limit: int,
        lockout: timedelta,
        event: SecurityEventValue,
    ) -> None:
        try:
            with self.sessions.begin() as session:
                if credential is not None:
                    current = session.scalar(
                        select(UserCredential)
                        .where(
                            UserCredential.organization_id == credential.organization_id,
                            UserCredential.user_id == credential.user_id,
                        )
                        .with_for_update()
                    )
                    if (
                        current is not None
                        and event.event_type != IdentityEventType.LOGIN_THROTTLED
                    ):
                        current.failed_login_count = min(
                            current.failed_login_count + 1, failure_limit
                        )
                        current.last_failed_at = occurred_at
                        if current.failed_login_count >= failure_limit:
                            current.locked_until = occurred_at + lockout
                session.add(_event_model(event))
        except SQLAlchemyError:
            raise IdentityUnavailable("Identity service unavailable") from None

    def establish_session(
        self,
        credential: CredentialRecord,
        new_session: NewSession,
        *,
        occurred_at: datetime,
        replacement_hash: str | None,
        event: SecurityEventValue,
    ) -> StoredSession | None:
        try:
            with self.sessions.begin() as session:
                row = session.execute(
                    select(UserCredential, Organization.status, User.status)
                    .join(
                        User,
                        (User.organization_id == UserCredential.organization_id)
                        & (User.id == UserCredential.user_id),
                    )
                    .join(Organization, Organization.id == User.organization_id)
                    .where(
                        UserCredential.organization_id == credential.organization_id,
                        UserCredential.user_id == credential.user_id,
                    )
                    .with_for_update(of=UserCredential)
                ).one_or_none()
                if row is None:
                    return None
                current, organization_status, user_status = row
                if (
                    current.password_hash != credential.password_hash
                    or organization_status != OrganizationStatus.ACTIVE
                    or user_status != UserStatus.ACTIVE
                    or (current.locked_until is not None and occurred_at < current.locked_until)
                ):
                    return None
                current.failed_login_count = 0
                current.locked_until = None
                current.last_successful_login_at = occurred_at
                if replacement_hash is not None:
                    current.password_hash = replacement_hash
                    current.password_changed_at = occurred_at
                persisted = _new_session_model(new_session)
                session.add_all((persisted, _event_model(event)))
                session.flush()
                return _stored_session(persisted)
        except (SQLAlchemyError, ValueError):
            raise IdentityUnavailable("Identity service unavailable") from None

    def resolve_hash(self, token_hash: str) -> StoredSession | None:
        try:
            with self.sessions() as session:
                record = session.scalar(
                    select(ServerSession).where(ServerSession.token_hash == token_hash)
                )
                return _stored_session(record) if record is not None else None
        except (SQLAlchemyError, ValueError):
            raise IdentityUnavailable("Identity service unavailable") from None

    def revoke(
        self,
        session_id: UUID,
        *,
        revoked_at: datetime,
        reason: str,
        event: SecurityEventValue,
    ) -> bool:
        try:
            with self.sessions.begin() as session:
                record = session.scalar(
                    select(ServerSession).where(ServerSession.id == session_id).with_for_update()
                )
                if record is None or record.revoked_at is not None:
                    return False
                record.revoked_at = revoked_at
                record.revocation_reason = reason
                session.add(_event_model(event))
                return True
        except SQLAlchemyError:
            raise IdentityUnavailable("Identity service unavailable") from None

    def rotate(
        self,
        current_session_id: UUID,
        replacement: NewSession,
        *,
        revoked_at: datetime,
        event: SecurityEventValue,
    ) -> StoredSession | None:
        try:
            with self.sessions.begin() as session:
                current = session.scalar(
                    select(ServerSession)
                    .where(ServerSession.id == current_session_id)
                    .with_for_update()
                )
                if (
                    current is None
                    or current.revoked_at is not None
                    or current.expires_at <= revoked_at
                    or replacement.rotated_from_id != current.id
                    or replacement.organization_id != current.organization_id
                    or replacement.user_id != current.user_id
                    or replacement.authenticated_at != current.authenticated_at
                    or replacement.expires_at != current.expires_at
                ):
                    return None
                current.revoked_at = revoked_at
                current.revocation_reason = "rotated"
                persisted = _new_session_model(replacement)
                session.add_all((persisted, _event_model(event)))
                session.flush()
                return _stored_session(persisted)
        except (SQLAlchemyError, ValueError):
            raise IdentityUnavailable("Identity service unavailable") from None


class SQLAlchemyOwnerBootstrapStore:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self.sessions = sessions

    def create_owner(
        self,
        request: BootstrapOwnerRequest,
        password_hash: str,
        *,
        created_at: datetime,
    ) -> BootstrapResult:
        organization_id = uuid4()
        user_id = uuid4()
        try:
            with self.sessions.begin() as session:
                session.execute(select(func.pg_advisory_xact_lock(_BOOTSTRAP_ADVISORY_LOCK)))
                if session.scalar(select(func.count()).select_from(Organization)):
                    raise BootstrapAlreadyCompleted("Owner bootstrap already completed")
                organization = Organization(
                    id=organization_id,
                    name=request.organization_name,
                    status=OrganizationStatus.ACTIVE,
                    created_at=created_at,
                    updated_at=created_at,
                )
                user = User(
                    id=user_id,
                    organization_id=organization_id,
                    name=request.owner_name,
                    email=request.email,
                    status=UserStatus.ACTIVE,
                    created_at=created_at,
                    updated_at=created_at,
                )
                credential = UserCredential(
                    organization_id=organization_id,
                    user_id=user_id,
                    password_hash=password_hash,
                    password_changed_at=created_at,
                    created_at=created_at,
                    updated_at=created_at,
                )
                roles = [
                    UserRole(
                        id=uuid4(),
                        organization_id=organization_id,
                        user_id=user_id,
                        role=role,
                        created_at=created_at,
                    )
                    for role in (Role.ADMIN, Role.FOUNDER, Role.RESEARCHER)
                ]
                event = IdentitySecurityEvent(
                    id=uuid4(),
                    event_type=IdentityEventType.OWNER_BOOTSTRAPPED,
                    outcome=IdentityEventOutcome.SUCCEEDED,
                    organization_id=organization_id,
                    user_id=user_id,
                    correlation_id=request.correlation_id,
                    reason_code="local_owner_created",
                    occurred_at=created_at,
                )
                session.add_all((organization, user, credential, *roles, event))
            return BootstrapResult(
                organization_id=organization_id,
                user_id=user_id,
                created_at=created_at,
            )
        except BootstrapAlreadyCompleted:
            raise
        except SQLAlchemyError:
            raise IdentityUnavailable("Identity service unavailable") from None
