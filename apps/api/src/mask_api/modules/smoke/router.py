import hmac
import json
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from mask_api.config import Settings
from mask_api.modules.smoke.contracts import SmokeRequest, SmokeResponse
from mask_api.modules.smoke.errors import SmokeNotFound, SmokeUnavailable
from mask_api.modules.smoke.services import SmokeService
from mask_api.modules.smoke.wiring import get_smoke_service

logger = logging.getLogger("mask")
Service = Annotated[SmokeService, Depends(get_smoke_service)]


def create_smoke_router(settings: Settings) -> APIRouter:
    def require_dev_token(x_dev_token: str = Header(default="")) -> None:
        expected = settings.dev_token.get_secret_value() if settings.dev_token else ""
        if not hmac.compare_digest(expected.encode(), x_dev_token.encode()):
            raise HTTPException(status_code=401, detail="Unauthorized")

    router = APIRouter(dependencies=[Depends(require_dev_token)])

    @router.post("/dev/jobs/smoke", response_model=SmokeResponse, status_code=202)
    def smoke(payload: SmokeRequest, request: Request, service: Service) -> SmokeResponse:
        try:
            return service.submit(payload.idempotency_key, UUID(request.state.correlation_id))
        except SmokeUnavailable:
            logger.warning(
                json.dumps(
                    {
                        "event": "smoke_enqueue_failed",
                        "correlation_id": request.state.correlation_id,
                    }
                )
            )
            raise HTTPException(503, "Smoke job service unavailable; retry same key") from None

    @router.get("/dev/jobs/{job_id}", response_model=SmokeResponse)
    def job_status(job_id: UUID, service: Service) -> SmokeResponse:
        try:
            return service.get(job_id)
        except SmokeNotFound:
            raise HTTPException(404, "Job not found") from None

    return router
