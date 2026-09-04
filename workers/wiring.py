from mask_api.config import get_settings
from mask_api.job_queue.wiring import get_job_queue

from workers.runtime import WorkerRuntime
from workers.smoke_handler import handle_smoke


def get_worker_runtime() -> WorkerRuntime:
    settings = get_settings()
    return WorkerRuntime(
        get_job_queue(),
        {"infrastructure.smoke": handle_smoke},
        lease_seconds=settings.job_lease_seconds,
        heartbeat_seconds=settings.worker_heartbeat_seconds,
        poll_seconds=settings.queue_poll_seconds,
    )
