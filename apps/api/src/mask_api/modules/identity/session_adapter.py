"""Adapt a hashed persistent session store to the authorization core's reader port."""

from dataclasses import dataclass

from pydantic import SecretStr

from mask_api.modules.identity.auth_ports import AuthenticationStore, TokenManager
from mask_api.modules.identity.contracts import SessionRecord


@dataclass(frozen=True)
class HashedSessionReader:
    store: AuthenticationStore
    tokens: TokenManager

    def resolve(self, token: SecretStr) -> SessionRecord | None:
        if not token.get_secret_value() or len(token.get_secret_value()) > 4096:
            return None
        stored = self.store.resolve_hash(self.tokens.digest(token))
        return stored.record if stored is not None else None
