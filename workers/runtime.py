import json
import logging
import random
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from threading import Event, Thread
from uuid import UUID, uuid4

from mask_api.job_queue.contracts import JobEnvelope, JobFailure
from mask_api.job_queue.errors import JobOwnershipLost, PermanentJobError, RetryableJobError
from mask_api.job_queue.ports import JobQueue
from pydantic import JsonValue

JobHandler = Callable[[JobEnvelope], dict[str, JsonValue]]


class WorkerRuntime:
    def __init__(
        self,
        queue: JobQueue,
        handlers: Mapping[str, JobHandler],
        *,
        lease_seconds: int,
        heartbeat_seconds: int,
        poll_seconds: float,
        worker_id: UUID | None = None,
        logger: logging.Logger | None = None,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        if lease_seconds <= heartbeat_seconds:
            raise ValueError("Lease must exceed heartbeat interval")
        if heartbeat_seconds < 1 or poll_seconds <= 0:
            raise ValueError("Worker intervals must be positive")
        self.queue = queue
        self.handlers = dict(handlers)
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self.poll_seconds = poll_seconds
        self.worker_id = worker_id or uuid4()
        self.logger = logger or logging.getLogger("mask.worker")
        self.jitter = jitter
        self.started_at = datetime.now(UTC)

    def _log(self, event: str, envelope: JobEnvelope | None = None) -> None:
        payload: dict[str, str | int] = {
            "event": event,
            "worker_id": str(self.worker_id),
        }
        if envelope is not None:
            payload.update(
                {
                    "job_id": str(envelope.job_id),
                    "correlation_id": str(envelope.correlation_id),
                    "attempt": envelope.attempt,
                    "attempt_limit": envelope.attempt_limit,
                }
            )
        self.logger.info(json.dumps(payload))

    def _maintain_lease(self, envelope: JobEnvelope, stop: Event, lost: Event) -> None:
        while not stop.wait(self.heartbeat_seconds):
            try:
                self.queue.touch_worker(self.worker_id, self.started_at)
                if not self.queue.heartbeat(
                    envelope.job_id,
                    envelope.lease_token,
                    self.worker_id,
                    self.lease_seconds,
                ):
                    lost.set()
                    return
            except Exception:
                # The main loop must not commit completion after uncertain ownership.
                lost.set()
                return

    def run_once(self) -> bool:
        envelope = self.queue.claim(self.worker_id, self.lease_seconds)
        if envelope is None:
            return False
        self._log("job_started", envelope)
        lease_stop = Event()
        lease_lost = Event()
        keeper = Thread(
            target=self._maintain_lease,
            args=(envelope, lease_stop, lease_lost),
            daemon=True,
            name=f"mask-lease-{envelope.job_id}",
        )
        keeper.start()
        failure: JobFailure | None = None
        output: dict[str, JsonValue] | None = None
        handler = self.handlers.get(envelope.job_type)
        try:
            if handler is None:
                raise PermanentJobError("unknown_job_type")
            output = handler(envelope)
        except RetryableJobError as error:
            failure = JobFailure(code=error.code, retryable=True, jitter_fraction=self.jitter())
        except PermanentJobError as error:
            failure = JobFailure(code=error.code, retryable=False, jitter_fraction=0)
        except Exception:
            failure = JobFailure(
                code="unexpected_handler_error", retryable=True, jitter_fraction=self.jitter()
            )
        finally:
            lease_stop.set()
            keeper.join(timeout=self.heartbeat_seconds + 1)

        if lease_lost.is_set():
            self._log("job_lease_lost", envelope)
            return True
        try:
            if failure is not None:
                status = self.queue.fail(envelope.job_id, envelope.lease_token, failure)
                self._log(f"job_{status.value}", envelope)
            else:
                status = self.queue.succeed(envelope.job_id, envelope.lease_token, output or {})
                self._log(f"job_{status.value}", envelope)
        except JobOwnershipLost:
            self._log("job_lease_lost", envelope)
        return True

    def run(self, stop: Event) -> int:
        self._log("worker_started")
        try:
            while not stop.is_set():
                try:
                    self.queue.touch_worker(self.worker_id, self.started_at)
                    processed = self.run_once()
                except Exception:
                    self._log("worker_dependency_unavailable")
                    processed = False
                if not processed:
                    stop.wait(self.poll_seconds)
        finally:
            try:
                self.queue.stop_worker(self.worker_id)
            except Exception:
                self._log("worker_stop_unconfirmed")
            self._log("worker_stopped")
        return 0
