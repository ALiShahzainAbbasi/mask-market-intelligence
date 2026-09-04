from typing import Literal

from pydantic import BaseModel


class Liveness(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["mask-api"] = "mask-api"


class Readiness(BaseModel):
    status: Literal["ready", "not_ready"]
    dependencies: dict[Literal["postgres"], Literal["up", "down"]]
