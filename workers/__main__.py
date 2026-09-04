"""Native Windows-compatible PostgreSQL worker entrypoint."""

import logging
import signal
from threading import Event

from workers.wiring import get_worker_runtime


def main() -> int:
    stop = Event()

    def request_stop(signum: int, frame: object) -> None:
        del signum, frame
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)
    settings_runtime = get_worker_runtime()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    return settings_runtime.run(stop)


if __name__ == "__main__":
    raise SystemExit(main())
