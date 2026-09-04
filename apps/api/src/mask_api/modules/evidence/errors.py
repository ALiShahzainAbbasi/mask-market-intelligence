class CollectionFailure(Exception):
    """A safe, classified collection failure suitable for job handling."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


class SourcePolicyDenied(CollectionFailure):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, retryable=False)


class SourcePolicyUnavailable(CollectionFailure):
    def __init__(self) -> None:
        super().__init__(
            "source_policy.unavailable",
            "The source policy registry is temporarily unavailable.",
            retryable=True,
        )


class FetchFailure(CollectionFailure):
    pass


class ParseFailure(CollectionFailure):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, retryable=False)


class PersistenceFailure(CollectionFailure):
    def __init__(self) -> None:
        super().__init__(
            "collection.persistence_failed",
            "The collection result could not be persisted safely.",
            retryable=True,
        )
