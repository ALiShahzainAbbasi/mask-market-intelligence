class JobQueueError(Exception):
    """Safe base error; driver details must not cross the adapter boundary."""


class IdempotencyConflict(JobQueueError):
    """A key was reused for a different immutable request."""


class JobOwnershipLost(JobQueueError):
    """The worker no longer owns the active lease."""


class RetryableJobError(Exception):
    def __init__(self, code: str = "retryable_handler_error") -> None:
        self.code = code
        super().__init__(code)


class PermanentJobError(Exception):
    def __init__(self, code: str = "permanent_handler_error") -> None:
        self.code = code
        super().__init__(code)
