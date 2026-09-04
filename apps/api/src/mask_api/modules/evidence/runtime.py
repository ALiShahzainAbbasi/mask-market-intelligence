import random
import time
from datetime import UTC, datetime


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return time.monotonic()


class SystemSleeper:
    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class SystemJitterSource:
    def __init__(self) -> None:
        self._random = random.SystemRandom()

    def fraction(self) -> float:
        return self._random.random()


class NeverCancelled:
    def is_cancelled(self) -> bool:
        return False
