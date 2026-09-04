from mask_api.modules.identity.security import Argon2idPasswordManager, Sha256TokenManager
from pydantic import SecretStr


def test_argon2id_hashes_and_verifies_without_exposing_password() -> None:
    manager = Argon2idPasswordManager()
    password = SecretStr("correct horse battery staple")
    password_hash = manager.hash(password)

    assert password_hash.startswith("$argon2id$")
    assert "correct horse" not in password_hash
    assert manager.verify(password_hash, password) is True
    assert manager.verify(password_hash, SecretStr("wrong password value")) is False
    assert manager.verify(None, password) is False
    assert manager.needs_rehash(password_hash) is False
    assert manager.needs_rehash("not-a-valid-hash") is True


def test_session_and_csrf_tokens_are_random_and_only_digests_are_stable() -> None:
    manager = Sha256TokenManager()
    first, first_digest = manager.issue()
    second, second_digest = manager.issue()

    assert first.get_secret_value() != second.get_secret_value()
    assert first_digest != second_digest
    assert len(first_digest) == len(second_digest) == 64
    assert first.get_secret_value() not in first_digest
    assert manager.digest(first) == first_digest
    assert manager.matches(first, first_digest) is True
    assert manager.matches(second, first_digest) is False
