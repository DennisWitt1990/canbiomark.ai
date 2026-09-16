"""Lifecycle management for the embedded H2O cluster.

Two failure modes were observed in production runs of the predecessor pipeline
(``MA_Extension/app/backend/app/ml/train.py``); both are handled here so that
neither the classification nor the regression runner has to repeat the logic.

1. **Restart race.** ``h2o.shutdown()`` returns before the JVM has released the
   port.  An ``h2o.init()`` that follows immediately connects to the dying
   instance and the next REST call fails with ``Connection refused``.  This hits
   every process that runs more than one job, so :meth:`H2OSession.start`
   retries and forces a real REST round trip, and :meth:`stop` waits until the
   port is actually free.

2. **Heap leak.** Python's ``del`` only drops the client-side handle; the frame
   stays in the JVM heap under its key.  Without an explicit removal the heap
   grows with every trained model and every uploaded frame until the cluster
   spends its time in garbage collection -- measured in an earlier run as one
   threshold taking over two hours instead of nine minutes.
   :meth:`release` removes the objects from the cluster itself.
"""
from __future__ import annotations

import logging
import os
import socket
import time
from typing import Any, Optional

from ..domain.errors import DomainError

_logger = logging.getLogger(__name__)

DEFAULT_H2O_PORT = 54321
_START_ATTEMPTS = 5
_PORT_RELEASE_TIMEOUT_SECONDS = 30.0


class H2OClusterError(DomainError):
    """The H2O cluster could not be started or became unreachable."""

    http_status_code = 500


class H2OSession:
    """Starts, cleans up and stops one embedded H2O cluster.

    Use it as a context manager so the cluster is always stopped, even when
    training raises::

        with H2OSession(max_memory="20g") as session:
            frame = session.upload(data_frame, categorical_columns=["Label"])
            ...
    """

    def __init__(self, max_memory: str = "20g", port: Optional[int] = None) -> None:
        self._max_memory = max_memory
        self._port = port or int(os.getenv("H2O_PORT", str(DEFAULT_H2O_PORT)))
        self._module: Any = None

    # -- context manager ---------------------------------------------------

    def __enter__(self) -> "H2OSession":
        self.start()
        return self

    def __exit__(self, exception_type, exception_value, traceback) -> None:
        self.stop()

    # -- lifecycle ---------------------------------------------------------

    @property
    def module(self) -> Any:
        """The imported ``h2o`` module; only valid after :meth:`start`."""
        if self._module is None:
            raise H2OClusterError("The H2O cluster has not been started.")
        return self._module

    def start(self) -> None:
        """Start the cluster, retrying past a still-shutting-down predecessor."""
        import h2o

        self._module = h2o
        last_error: Optional[Exception] = None

        for attempt in range(1, _START_ATTEMPTS + 1):
            try:
                h2o.init(nthreads=-1, max_mem_size=self._max_memory, port=self._port)
                # Force a real REST round trip: a half-dead connection surfaces
                # here rather than in the middle of training.
                h2o.cluster().show_status()
                _logger.info("H2O cluster is up on port %s.", self._port)
                return
            except Exception as error:  # noqa: BLE001 - any connection problem
                last_error = error
                _logger.warning(
                    "H2O start attempt %s/%s failed: %s", attempt, _START_ATTEMPTS, error
                )
                self._close_connection_quietly()
                time.sleep(3 * attempt)

        raise H2OClusterError(f"The H2O cluster could not be started: {last_error}")

    def stop(self) -> None:
        """Shut the cluster down and wait until the port is free again."""
        if self._module is None:
            return

        try:
            self._module.cluster().shutdown()
        except Exception:  # noqa: BLE001 - shutting down is best effort
            _logger.debug("H2O shutdown call failed; continuing.", exc_info=True)
        self._close_connection_quietly()

        deadline = time.time() + _PORT_RELEASE_TIMEOUT_SECONDS
        while time.time() < deadline:
            if not self._is_port_open():
                _logger.info("H2O cluster stopped and port %s released.", self._port)
                self._module = None
                return
            time.sleep(0.5)

        _logger.warning(
            "H2O port %s was still open after %.0f s.",
            self._port,
            _PORT_RELEASE_TIMEOUT_SECONDS,
        )
        self._module = None

    def remove_all(self) -> None:
        """Drop every object in the cluster; used right after a fresh start."""
        try:
            self.module.remove_all()
        except Exception:  # noqa: BLE001
            _logger.debug("h2o.remove_all() failed; continuing.", exc_info=True)

    # -- data handling -----------------------------------------------------

    def upload(self, table, categorical_columns: tuple[str, ...] = ()):
        """Upload a pandas frame, marking the given columns as categorical."""
        column_types = {name: "enum" for name in categorical_columns}
        frame = self.module.H2OFrame(table, column_types=column_types or None)
        for column_name in categorical_columns:
            frame[column_name] = frame[column_name].asfactor()
        return frame

    def release(self, *cluster_objects: Any) -> None:
        """Remove frames and models from the **cluster**, not just from Python.

        Without this the JVM heap keeps every intermediate frame alive and the
        cluster degrades into garbage-collection thrashing.
        """
        for cluster_object in cluster_objects:
            if cluster_object is None:
                continue
            try:
                self.module.remove(cluster_object)
            except Exception:  # noqa: BLE001 - never let cleanup break a run
                _logger.debug("Could not remove an H2O object.", exc_info=True)

    def save_model(self, model: Any, target_directory) -> str:
        """Persist a trained model and return its path."""
        target_directory.mkdir(parents=True, exist_ok=True)
        return self.module.save_model(
            model=model, path=str(target_directory), force=True
        )

    # -- internals ---------------------------------------------------------

    def _close_connection_quietly(self) -> None:
        if self._module is None:
            return
        try:
            self._module.connection().close()
        except Exception:  # noqa: BLE001
            pass

    def _is_port_open(self, timeout: float = 1.0) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe_socket:
            probe_socket.settimeout(timeout)
            return probe_socket.connect_ex(("127.0.0.1", self._port)) == 0
