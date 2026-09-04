from typing import Annotated

from fastapi import APIRouter, Depends, Response

from mask_api.health import readiness_report
from mask_api.modules.health.contracts import Liveness, Readiness

router = APIRouter()


@router.get("/health/live", response_model=Liveness)
def live() -> Liveness:
    return Liveness()


@router.get("/health/ready", response_model=Readiness, responses={503: {"model": Readiness}})
def ready(response: Response, result: Annotated[Readiness, Depends(readiness_report)]) -> Readiness:
    if result.status != "ready":
        response.status_code = 503
    return result
