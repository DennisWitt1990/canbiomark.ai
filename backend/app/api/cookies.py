"""Sets and clears the session cookie consistently."""
from __future__ import annotations

from fastapi import Response

from ..config.settings import ApplicationSettings


class SessionCookieWriter:
    """Knows the single correct cookie configuration for this application."""

    def __init__(self, settings: ApplicationSettings) -> None:
        self._settings = settings

    def attach(self, response: Response, cookie_value: str) -> None:
        response.set_cookie(
            key=self._settings.session_cookie_name,
            value=cookie_value,
            httponly=True,          # not readable from JavaScript
            samesite="lax",
            secure=self._settings.session_cookie_secure,  # set true behind HTTPS
            max_age=self._settings.session_lifetime_seconds,
            path="/",
        )

    def clear(self, response: Response) -> None:
        response.delete_cookie(
            key=self._settings.session_cookie_name,
            httponly=True,
            samesite="lax",
            secure=self._settings.session_cookie_secure,
            path="/",
        )
