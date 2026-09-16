"""Cross-origin configuration for the development frontend."""
from __future__ import annotations

import re
from typing import Sequence

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# During development Vite serves the frontend from another port, so the API has
# to allow that origin explicitly — with credentials, because the session lives
# in a cookie.
_LOCAL_ORIGIN_PATTERN = re.compile(
    r"^https?://(localhost|127\.0\.0\.1|host\.docker\.internal)(:\d+)?$"
)


class CorsConfigurator:
    """Adds the CORS middleware with a safe, explicit origin list."""

    def __init__(self, configured_origins: Sequence[str]) -> None:
        self._configured_origins = list(configured_origins)

    def apply(self, application: FastAPI) -> None:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=self._configured_origins,
            allow_origin_regex=_LOCAL_ORIGIN_PATTERN.pattern,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "Accept"],
        )
