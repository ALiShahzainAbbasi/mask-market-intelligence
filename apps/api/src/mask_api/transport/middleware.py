import json
import logging
import time
from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

from fastapi import FastAPI, Request, Response

from mask_api.transport.errors import safe_error

logger = logging.getLogger("mask")


def install_http_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def correlation(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        try:
            correlation_id = UUID(request.headers.get("x-correlation-id", ""))
        except ValueError:
            correlation_id = uuid4()
        request.state.correlation_id = str(correlation_id)
        started = time.monotonic()
        try:
            response = await call_next(request)
        except Exception as exc:
            response = await safe_error(request, exc)
        response.headers["X-Correlation-ID"] = str(correlation_id)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        logger.info(
            json.dumps(
                {
                    "event": "http_request",
                    "correlation_id": str(correlation_id),
                    "method": request.method,
                    "status": response.status_code,
                    "duration_ms": round((time.monotonic() - started) * 1000),
                }
            )
        )
        return response
