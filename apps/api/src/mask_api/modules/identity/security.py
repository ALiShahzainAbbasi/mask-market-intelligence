"""Maintained password hashing and standard-library opaque-token generation."""

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type
from pydantic import SecretStr


class Argon2idPasswordManager:
    def __init__(self, hasher: PasswordHasher | None = None) -> None:
        self._hasher = hasher or PasswordHasher(type=Type.ID)
        # Equalize the expensive verification path for unknown accounts. This
        # random dummy hash is process-local and is never an account credential.
        self._dummy_hash = self._hasher.hash(secrets.token_urlsafe(32))

    def hash(self, password: SecretStr) -> str:
        return self._hasher.hash(password.get_secret_value())

    def verify(self, password_hash: str | None, password: SecretStr) -> bool:
        candidate_hash = password_hash or self._dummy_hash
        try:
            return self._hasher.verify(candidate_hash, password.get_secret_value())
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        try:
            return self._hasher.check_needs_rehash(password_hash)
        except (VerificationError, InvalidHashError):
            return True


class Sha256TokenManager:
    """Generate 256-bit bearer secrets and persist only fixed-length digests."""

    def issue(self) -> tuple[SecretStr, str]:
        token = SecretStr(secrets.token_urlsafe(32))
        return token, self.digest(token)

    def digest(self, token: SecretStr) -> str:
        return hashlib.sha256(token.get_secret_value().encode("utf-8")).hexdigest()

    def matches(self, token: SecretStr, expected_digest: str) -> bool:
        return hmac.compare_digest(self.digest(token), expected_digest)
