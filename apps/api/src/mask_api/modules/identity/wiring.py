from datetime import UTC, datetime, timedelta
from functools import lru_cache

from mask_api.config import get_settings
from mask_api.database import get_session_factory
from mask_api.modules.identity.auth_repository import (
    SQLAlchemyAuthenticationStore,
    SQLAlchemyOwnerBootstrapStore,
)
from mask_api.modules.identity.auth_services import (
    LocalAuthenticationService,
    OwnerBootstrapService,
)
from mask_api.modules.identity.repository import SQLAlchemyMembershipReader
from mask_api.modules.identity.security import Argon2idPasswordManager, Sha256TokenManager
from mask_api.modules.identity.services import IdentityService
from mask_api.modules.identity.session_adapter import HashedSessionReader


def utc_now() -> datetime:
    return datetime.now(UTC)


@lru_cache
def get_password_manager() -> Argon2idPasswordManager:
    return Argon2idPasswordManager()


@lru_cache
def get_token_manager() -> Sha256TokenManager:
    return Sha256TokenManager()


@lru_cache
def get_authentication_store() -> SQLAlchemyAuthenticationStore:
    return SQLAlchemyAuthenticationStore(get_session_factory())


@lru_cache
def get_local_authentication_service() -> LocalAuthenticationService:
    settings = get_settings()
    return LocalAuthenticationService(
        store=get_authentication_store(),
        passwords=get_password_manager(),
        tokens=get_token_manager(),
        clock=utc_now,
        session_lifetime=timedelta(hours=settings.auth_session_hours),
        failure_limit=settings.auth_failure_limit,
        lockout=timedelta(seconds=settings.auth_lockout_seconds),
    )


@lru_cache
def get_identity_service() -> IdentityService:
    settings = get_settings()
    store = get_authentication_store()
    return IdentityService(
        sessions=HashedSessionReader(store=store, tokens=get_token_manager()),
        memberships=SQLAlchemyMembershipReader(get_session_factory()),
        clock=utc_now,
        recent_auth_max_age=timedelta(minutes=settings.auth_recent_minutes),
    )


@lru_cache
def get_owner_bootstrap_service() -> OwnerBootstrapService:
    return OwnerBootstrapService(
        store=SQLAlchemyOwnerBootstrapStore(get_session_factory()),
        passwords=get_password_manager(),
        clock=utc_now,
    )
