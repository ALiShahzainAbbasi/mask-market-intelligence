from pydantic import BaseModel


class ErrorResponse(BaseModel):
    error: str
    correlation_id: str | None = None
