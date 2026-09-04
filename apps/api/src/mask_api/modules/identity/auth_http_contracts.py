from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class LoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    organization_id: UUID
    email: str = Field(min_length=4, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=256)


class SessionResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    organization_id: UUID
    user_id: UUID
    expires_at: datetime
