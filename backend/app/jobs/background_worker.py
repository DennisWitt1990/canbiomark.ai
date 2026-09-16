"""Starts daemon threads for long-running work."""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable

_logger = logging.getLogger(__name__)


class BackgroundWorker:
    """Runs a callable in a daemon thread and logs any escaping exception."""

    def __init__(self, thread_name_prefix: str = "canbiomark-worker") -> None:
        self._thread_name_prefix = thread_name_prefix
        self._started_threads: list[threading.Thread] = []

    def start(self, target: Callable[..., Any], *arguments: Any) -> threading.Thread:
        thread = threading.Thread(
            target=self._run_guarded,
            args=(target, *arguments),
            name=f"{self._thread_name_prefix}-{len(self._started_threads) + 1}",
            daemon=True,
        )
        self._started_threads.append(thread)
        thread.start()
        return thread

    @staticmethod
    def _run_guarded(target: Callable[..., Any], *arguments: Any) -> None:
        try:
            target(*arguments)
        except Exception:  # noqa: BLE001 - a worker must never kill the process
            _logger.exception("Background task %s failed.", getattr(target, "__name__", target))
