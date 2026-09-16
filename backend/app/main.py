"""ASGI entry point: ``uvicorn app.main:app``."""
from __future__ import annotations

import logging
import os

from .application import create_application


def _configure_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
    )


_configure_logging()

app = create_application()
