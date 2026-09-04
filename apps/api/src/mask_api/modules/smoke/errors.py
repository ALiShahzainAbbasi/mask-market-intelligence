class SmokeUnavailable(Exception):
    """Transient infrastructure failure; safe for transport/worker translation."""


class SmokeNotFound(Exception):
    """The requested infrastructure job does not exist."""
