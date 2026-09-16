"""Translates domain exceptions into HTTP responses in a single place."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..domain.errors import DomainError

_logger = logging.getLogger(__name__)


class DomainErrorHandler:
    """Registers the exception handlers on a FastAPI application."""

    def register(self, application: FastAPI) -> None:
        application.add_exception_handler(DomainError, self._handle_domain_error)
        application.add_exception_handler(Exception, self._handle_unexpected_error)

    @staticmethod
    async def _handle_domain_error(_: Request, error: Exception) -> JSONResponse:
        assert isinstance(error, DomainError)
        return JSONResponse(
            status_code=error.http_status_code,
            content={"detail": error.message},
        )

    @staticmethod
    async def _handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
        _logger.exception("Unhandled error while serving %s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "An unexpected server error occurred."},
        )
