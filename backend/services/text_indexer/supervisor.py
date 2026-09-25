from __future__ import annotations

import signal

from .config import Settings
from .worker import Worker


def run_worker(settings: Settings) -> None:
    """Importable multiprocessing entry point for one isolated worker slot."""
    # The supervisor owns service lifecycle. Ignore terminal Ctrl-C in children
    # so it can stop the complete pool without child KeyboardInterrupt traces.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    Worker(settings).run()
