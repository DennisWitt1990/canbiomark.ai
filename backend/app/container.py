"""Composition root.

Every service is constructed exactly once here and wired together by
constructor injection.  Nothing else in the application reaches for a global:
routers receive what they need through FastAPI dependencies that read from this
container.
"""
from __future__ import annotations

import logging
from functools import cached_property

from .config.settings import ApplicationSettings, get_settings
from .database.connection import DatabaseConnectionFactory
from .database.repositories.audit_repository import AuditRepository
from .database.repositories.session_repository import SessionRepository
from .database.repositories.user_repository import UserRepository
from .database.schema import SchemaInitializer
from .domain.dataset_import import DatasetImportJob
from .domain.simbu import BatchJob
from .jobs.background_worker import BackgroundWorker
from .jobs.job_registry import JobRegistry
from .security.password_hasher import PasswordHasher
from .security.password_policy import PasswordPolicy
from .security.session_token import SessionTokenFactory
from .services.anndata_compatibility import AnnDataCompatibilityConverter
from .services.ai_suite_dataset import AiSuiteDatasetPreparer
from .services.ai_suite_service import AiSuiteJob, AiSuiteService
from .services.authentication_service import AuthenticationService
from .services.batch_definition_parser import BatchDefinitionParser
from .services.cell_selection_service import CellSelectionService
from .services.dataset_download import DatasetDownloader
from .services.dataset_import_service import DatasetImportService
from .services.dataset_search_service import DatasetSearchService
from .services.h5ad_inspector import H5adInspector
from .services.regression_runner import RegressionRunner
from .services.tls_context import TlsContextProvider
from .services.experiment_catalog_service import ExperimentCatalogService
from .services.simbu_runner import SimBuRunner
from .services.tissue_batch_service import TissueBatchService
from .services.tissue_generator_service import TissueGeneratorService
from .services.user_administration_service import UserAdministrationService
from .services.workspace_service import WorkspaceService

_logger = logging.getLogger(__name__)


class ServiceContainer:
    """Lazily builds and caches every service the application needs."""

    def __init__(self, settings: ApplicationSettings | None = None) -> None:
        self._settings = settings or get_settings()

    @property
    def settings(self) -> ApplicationSettings:
        return self._settings

    # -- infrastructure ----------------------------------------------------

    @cached_property
    def connection_factory(self) -> DatabaseConnectionFactory:
        return DatabaseConnectionFactory(self._settings.database_file)

    @cached_property
    def password_hasher(self) -> PasswordHasher:
        return PasswordHasher(self._settings.password_hash_iterations)

    @cached_property
    def password_policy(self) -> PasswordPolicy:
        return PasswordPolicy(self._settings.minimum_password_length)

    @cached_property
    def session_token_factory(self) -> SessionTokenFactory:
        return SessionTokenFactory()

    @cached_property
    def background_worker(self) -> BackgroundWorker:
        return BackgroundWorker()

    # -- repositories ------------------------------------------------------

    @cached_property
    def user_repository(self) -> UserRepository:
        return UserRepository(self.connection_factory)

    @cached_property
    def session_repository(self) -> SessionRepository:
        return SessionRepository(self.connection_factory)

    @cached_property
    def audit_repository(self) -> AuditRepository:
        return AuditRepository(self.connection_factory)

    # -- services ----------------------------------------------------------

    @cached_property
    def workspace_service(self) -> WorkspaceService:
        return WorkspaceService(self._settings.user_workspaces_directory)

    @cached_property
    def authentication_service(self) -> AuthenticationService:
        return AuthenticationService(
            user_repository=self.user_repository,
            session_repository=self.session_repository,
            audit_repository=self.audit_repository,
            password_hasher=self.password_hasher,
            password_policy=self.password_policy,
            session_token_factory=self.session_token_factory,
            session_lifetime_seconds=self._settings.session_lifetime_seconds,
        )

    @cached_property
    def user_administration_service(self) -> UserAdministrationService:
        return UserAdministrationService(
            user_repository=self.user_repository,
            session_repository=self.session_repository,
            audit_repository=self.audit_repository,
            workspace_service=self.workspace_service,
            password_hasher=self.password_hasher,
            password_policy=self.password_policy,
            default_quota_bytes=self._settings.default_user_quota_bytes,
        )

    @cached_property
    def experiment_catalog_service(self) -> ExperimentCatalogService:
        return ExperimentCatalogService(self._settings.shared_input_directory)

    @cached_property
    def cell_selection_service(self) -> CellSelectionService:
        return CellSelectionService(self.experiment_catalog_service)

    @cached_property
    def simbu_runner(self) -> SimBuRunner:
        return SimBuRunner(
            self._settings.simbu_r_script, self._settings.simbu_task_timeout_seconds
        )

    @cached_property
    def tissue_generator_service(self) -> TissueGeneratorService:
        return TissueGeneratorService(self.simbu_runner)

    @cached_property
    def batch_job_registry(self) -> JobRegistry[BatchJob]:
        return JobRegistry("batch job")

    @cached_property
    def tissue_batch_service(self) -> TissueBatchService:
        return TissueBatchService(
            simbu_runner=self.simbu_runner,
            definition_parser=BatchDefinitionParser(),
            job_registry=self.batch_job_registry,
            background_worker=self.background_worker,
        )

    @cached_property
    def ai_suite_job_registry(self) -> JobRegistry[AiSuiteJob]:
        return JobRegistry("AI suite job")

    @cached_property
    def ai_suite_service(self) -> AiSuiteService:
        return AiSuiteService(
            dataset_preparer=AiSuiteDatasetPreparer(),
            job_registry=self.ai_suite_job_registry,
            background_worker=self.background_worker,
            regression_runner=RegressionRunner(),
            h2o_max_memory=self._settings.h2o_max_memory,
        )

    # -- dataset import ----------------------------------------------------

    @cached_property
    def tls_context_provider(self) -> TlsContextProvider:
        return TlsContextProvider(
            certificate_bundle_path=self._settings.tls_certificate_bundle,
            allow_insecure=self._settings.allow_insecure_downloads,
        )

    @cached_property
    def dataset_search_service(self) -> DatasetSearchService:
        return DatasetSearchService(tls_context_provider=self.tls_context_provider)

    @cached_property
    def dataset_downloader(self) -> DatasetDownloader:
        return DatasetDownloader(
            tls_context_provider=self.tls_context_provider,
            maximum_file_size_bytes=self._settings.maximum_dataset_download_bytes,
        )

    @cached_property
    def h5ad_inspector(self) -> H5adInspector:
        return H5adInspector()

    @cached_property
    def anndata_compatibility_converter(self) -> AnnDataCompatibilityConverter:
        return AnnDataCompatibilityConverter()

    @cached_property
    def dataset_import_job_registry(self) -> JobRegistry[DatasetImportJob]:
        return JobRegistry("dataset import")

    @cached_property
    def dataset_import_service(self) -> DatasetImportService:
        return DatasetImportService(
            search_service=self.dataset_search_service,
            downloader=self.dataset_downloader,
            inspector=self.h5ad_inspector,
            compatibility_converter=self.anndata_compatibility_converter,
            job_registry=self.dataset_import_job_registry,
            background_worker=self.background_worker,
            catalogue_directory=self._settings.shared_input_directory,
            staging_root=self._settings.dataset_import_staging_directory,
            conversion_python_executable=self._settings.dataset_conversion_python,
        )

    # -- start up ----------------------------------------------------------

    def initialize(self) -> None:
        """Create the schema, the administrator account and the data folders."""
        self._settings.data_directory.mkdir(parents=True, exist_ok=True)
        self._settings.user_workspaces_directory.mkdir(parents=True, exist_ok=True)
        self._settings.dataset_import_staging_directory.mkdir(parents=True, exist_ok=True)

        SchemaInitializer(self.connection_factory).initialize()

        generated_password = self.authentication_service.ensure_administrator_exists(
            username=self._settings.bootstrap_admin_username,
            password=self._settings.bootstrap_admin_password,
            display_name=self._settings.bootstrap_admin_display_name,
            quota_bytes=self._settings.default_user_quota_bytes,
        )
        if generated_password and not self._settings.bootstrap_admin_password:
            _logger.warning(
                "=" * 72
                + "\nNo ADMIN_PASSWORD was configured, so an administrator was "
                "created with a random password:\n"
                f"    username: {self._settings.bootstrap_admin_username}\n"
                f"    password: {generated_password}\n"
                "Sign in and change it immediately; this is printed only once.\n"
                + "=" * 72
            )

        orphaned_imports = (
            self.dataset_import_service.discard_orphaned_staging_directories()
        )
        if orphaned_imports:
            _logger.info(
                "Cleared %s interrupted dataset import(s) from disk.", orphaned_imports
            )

        removed_sessions = self.session_repository.delete_expired()
        if removed_sessions:
            _logger.info("Removed %s expired session(s).", removed_sessions)
