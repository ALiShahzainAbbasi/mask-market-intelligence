from mask_api.job_queue.wiring import get_job_queue
from mask_api.modules.smoke.repository import JobQueueSmokeRepository
from mask_api.modules.smoke.services import SmokeService


def get_smoke_service() -> SmokeService:
    return SmokeService(JobQueueSmokeRepository(get_job_queue()))
