"""Compatibility exports; new code uses the job_queue package directly."""

from mask_api.job_queue.models import JobRecord, WorkerHeartbeat

__all__ = ["JobRecord", "WorkerHeartbeat"]
