"""Application factory.

``create_application`` builds the container, wires the routers and registers
the error handlers.  ``main.py`` only calls it, which keeps the module import
free of side effects and makes the app constructible in a test.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api.cors import CorsConfigurator
from .api.error_handlers import DomainErrorHandler
from .api.routers.administration_router import router as administration_router
from .api.routers.ai_suite_router import router as ai_suite_router
from .api.routers.authentication_router import router as authentication_router
from .api.routers.cell_selection_router import router as cell_selection_router
from .api.routers.dataset_import_router import router as dataset_import_router
from .api.routers.tissue_batch_router import router as tissue_batch_router
from .api.routers.tissue_generator_router import router as tissue_generator_router
from .api.routers.workspace_router import router as workspace_router
from .config.settings import ApplicationSettings, get_settings
from .container import ServiceContainer

_logger = logging.getLogger(__name__)

API_PREFIX = "/api"


class ApplicationFactory:
    """Assembles the FastAPI application from its parts."""

    def __init__(self, settings: ApplicationSettings | None = None) -> None:
        self._settings = settings or get_settings()
        self._container = ServiceContainer(self._settings)

    def build(self) -> FastAPI:
        application = FastAPI(
            title="CanBiomark.ai API",
            version=__version__,
            description=(
                "Synthetic bulk RNA-seq generation and benchmarking. "
                "Authentication uses username and password with server-side sessions."
            ),
        )
        application.state.container = self._container

        self._container.initialize()

        CorsConfigurator(self._settings.allowed_browser_origins).apply(application)
        DomainErrorHandler().register(application)

        application.include_router(self._build_api_router())
        self._mount_frontend(application)
        return application

    # -- parts -------------------------------------------------------------

    def _build_api_router(self) -> APIRouter:
        api_router = APIRouter(prefix=API_PREFIX)

        @api_router.get("/health", tags=["operations"])
        def read_health() -> dict:
            """Liveness probe; the only endpoint that needs no session."""
            return {"status": "ok", "version": __version__}

        api_router.include_router(authentication_router)
        api_router.include_router(administration_router)
        api_router.include_router(workspace_router)
        api_router.include_router(dataset_import_router)
        api_router.include_router(cell_selection_router)
        api_router.include_router(tissue_generator_router)
        api_router.include_router(tissue_batch_router)
        api_router.include_router(ai_suite_router)
        return api_router

    def _mount_frontend(self, application: FastAPI) -> None:
        """Serve the built single-page app from the same origin in production."""
        if not self._settings.serve_bundled_frontend:
            return

        bundle_directory = self._settings.frontend_bundle_directory
        if not bundle_directory.exists():
            _logger.warning(
                "SERVE_FRONTEND is on but %s does not exist.", bundle_directory
            )
            return

        application.mount(
            "/",
            StaticFiles(directory=bundle_directory, html=True),
            name="frontend",
        )
        _logger.info("Serving the frontend bundle from %s", bundle_directory)


def create_application(settings: ApplicationSettings | None = None) -> FastAPI:
    """Convenience wrapper used by ``main`` and by tests."""
    return ApplicationFactory(settings).build()
