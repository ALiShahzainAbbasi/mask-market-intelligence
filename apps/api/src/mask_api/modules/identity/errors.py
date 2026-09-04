class AuthenticationRequired(Exception):
    """Missing, invalid, expired, or revoked server session."""


class AccessDenied(Exception):
    """Authenticated actor cannot use the requested tenant/permission/role."""


class RecentAuthenticationRequired(Exception):
    """Sensitive action needs provider-backed reauthentication."""


class IdentityUnavailable(Exception):
    """Identity dependency failed; never permit access using a cached fallback."""


class InvalidCredentials(Exception):
    """Generic login denial; never reveal whether an account exists."""


class LoginRateLimited(Exception):
    """A known account is temporarily locked after bounded failed attempts."""


class InvalidCsrfToken(Exception):
    """A state-changing session request did not prove its CSRF secret."""


class PasswordPolicyViolation(Exception):
    """A new local password does not meet the bounded private-MVP policy."""


class BootstrapAlreadyCompleted(Exception):
    """The one-time owner bootstrap cannot run on a non-empty identity store."""
