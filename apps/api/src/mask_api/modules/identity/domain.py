from enum import StrEnum
from types import MappingProxyType


class Role(StrEnum):
    RESEARCHER = "researcher"
    REVIEWER = "reviewer"
    SALES = "sales"
    TECHNICAL = "technical"
    FOUNDER = "founder"
    ADMIN = "admin"


class OrganizationStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class UserStatus(StrEnum):
    INVITED = "invited"
    ACTIVE = "active"
    SUSPENDED = "suspended"


class IdentityEventType(StrEnum):
    OWNER_BOOTSTRAPPED = "owner_bootstrapped"
    LOGIN_SUCCEEDED = "login_succeeded"
    LOGIN_FAILED = "login_failed"
    LOGIN_THROTTLED = "login_throttled"
    SESSION_ROTATED = "session_rotated"
    SESSION_REVOKED = "session_revoked"


class IdentityEventOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    DENIED = "denied"


def normalize_email(value: str) -> str:
    """Canonical login locator only; it is never authorization evidence."""
    normalized = value.strip().lower()
    if (
        not 4 <= len(normalized) <= 254
        or normalized.count("@") != 1
        or any(character.isspace() for character in normalized)
    ):
        raise ValueError("Invalid email address")
    local, domain = normalized.split("@", maxsplit=1)
    if not local or not domain or domain.startswith(".") or domain.endswith("."):
        raise ValueError("Invalid email address")
    return normalized


class Permission(StrEnum):
    """Phase 2 role gates only; later workflows need their own explicit grants."""

    MARKET_READ = "market.read"
    MARKET_CREATE = "market.create"
    MARKET_UPDATE = "market.update"
    MARKET_ARCHIVE = "market.archive"
    RESEARCH_PLAN_DRAFT = "research_plan.draft"
    RESEARCH_PLAN_APPROVE = "research_plan.approve"
    MEMBERSHIP_MANAGE = "membership.manage"


PERMISSION_ROLES = MappingProxyType(
    {
        Permission.MARKET_READ: frozenset(
            {Role.RESEARCHER, Role.REVIEWER, Role.SALES, Role.TECHNICAL, Role.FOUNDER, Role.ADMIN}
        ),
        Permission.MARKET_CREATE: frozenset({Role.RESEARCHER}),
        Permission.MARKET_UPDATE: frozenset({Role.RESEARCHER}),
        Permission.MARKET_ARCHIVE: frozenset({Role.RESEARCHER}),
        Permission.RESEARCH_PLAN_DRAFT: frozenset({Role.RESEARCHER}),
        Permission.RESEARCH_PLAN_APPROVE: frozenset({Role.REVIEWER}),
        Permission.MEMBERSHIP_MANAGE: frozenset({Role.ADMIN}),
    }
)
RECENT_AUTH_PERMISSIONS = frozenset({Permission.MEMBERSHIP_MANAGE})


def role_permits(roles: frozenset[Role], permission: Permission, acting_role: Role) -> bool:
    """No wildcard role, role hierarchy, or automatic union acting-role selection."""
    return acting_role in roles and acting_role in PERMISSION_ROLES.get(permission, frozenset())
