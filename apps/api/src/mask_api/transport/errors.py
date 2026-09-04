import json
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from mask_api.transport.schemas import ErrorResponse

logger = logging.getLogger("mask")


async def validation_error(request: Request, _: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            error="Invalid request",
            correlation_id=getattr(request.state, "correlation_id", None),
        ).model_dump(),
    )


async def safe_error(request: Request, _: Exception) -> JSONResponse:
    cid = getattr(request.state, "correlation_id", None)
    logger.error(json.dumps({"event": "request_failed", "correlation_id": cid}))
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(error="Internal service error", correlation_id=cid).model_dump(),
        headers={"X-Correlation-ID": cid or "", "Cache-Control": "no-store"},
    )


def install_error_handlers(app: FastAPI) -> None:
    app.exception_handler(RequestValidationError)(validation_error)
    app.exception_handler(Exception)(safe_error)
