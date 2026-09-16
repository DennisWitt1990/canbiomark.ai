"""Central, typed configuration for the CanBiomark.ai backend.

Every runtime knob lives on :class:`ApplicationSettings`.  Nothing else in the
code base reads ``os.environ`` directly, which keeps configuration discoverable
and makes the whole application testable by constructing a settings object by
hand.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional, Sequence

_BYTES_PER_GIGABYTE = 1024 * 1024 * 1024


def _read_text(variable_name: str, fallback: str) -> str:
    return (os.getenv(variable_name) or fallback).strip()


def _read_integer(variable_name: str, fallback: int) -> int:
    raw_value = (os.getenv(variable_name) or "").strip()
    if not raw_value:
        return fallback
    try:
        return int(raw_value)
    except ValueError:
        return fallback


def _read_boolean(variable_name: str, fallback: bool) -> bool:
    raw_value = (os.getenv(variable_name) or "").strip().lower()
    if not raw_value:
        return fallback
    return raw_value in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ApplicationSettings:
    """Immutable snapshot of the environment the application runs in."""

    # --- Storage -----------------------------------------------------------
    data_directory: Path
    database_file: Path
    shared_input_directory: Path

    # --- HTTP / session ----------------------------------------------------
    session_cookie_name: str
    session_lifetime_hours: int
    session_cookie_secure: bool
    allowed_browser_origins: Sequence[str]

    # --- Password policy ---------------------------------------------------
    password_hash_iterations: int
    minimum_password_length: int

    # --- Bootstrap administrator ------------------------------------------
    bootstrap_admin_username: str
    bootstrap_admin_password: str
    bootstrap_admin_display_name: str

    # --- Defaults for newly created accounts -------------------------------
    default_user_quota_bytes: int

    # --- Dataset import ----------------------------------------------------
    dataset_import_staging_directory: Path
    dataset_conversion_python: Optional[str]
    maximum_dataset_download_bytes: Optional[int]
    tls_certificate_bundle: Optional[str]
    allow_insecure_downloads: bool

    # --- External tooling --------------------------------------------------
    simbu_r_script: Path
    simbu_task_timeout_seconds: int
    h2o_max_memory: str

    # --- Frontend hosting --------------------------------------------------
    serve_bundled_frontend: bool
    frontend_bundle_directory: Path

    extra: dict = field(default_factory=dict)

    @classmethod
    def from_environment(cls) -> "ApplicationSettings":
        data_directory = Path(_read_text("DATA_DIR", "/app/data"))
        backend_root = Path(__file__).resolve().parents[2]
        project_root = backend_root.parent

        return cls(
            data_directory=data_directory,
            database_file=Path(
                _read_text("DB_PATH", str(data_directory / "canbiomark.sqlite"))
            ),
            shared_input_directory=Path(
                _read_text("SHARED_INPUT_DIR", str(data_directory))
            ),
            session_cookie_name=_read_text("SESSION_COOKIE_NAME", "canbiomark_session"),
            session_lifetime_hours=_read_integer("SESSION_LIFETIME_HOURS", 12),
            session_cookie_secure=_read_boolean("SESSION_COOKIE_SECURE", False),
            allowed_browser_origins=tuple(
                origin.strip()
                for origin in _read_text("ALLOWED_ORIGINS", "").split(",")
                if origin.strip()
            ),
            password_hash_iterations=_read_integer("PASSWORD_HASH_ITERATIONS", 240_000),
            minimum_password_length=_read_integer("MINIMUM_PASSWORD_LENGTH", 10),
            bootstrap_admin_username=_read_text("ADMIN_USERNAME", "admin"),
            bootstrap_admin_password=_read_text("ADMIN_PASSWORD", ""),
            bootstrap_admin_display_name=_read_text(
                "ADMIN_DISPLAY_NAME", "Administrator"
            ),
            default_user_quota_bytes=_read_integer("DEFAULT_QUOTA_GB", 50)
            * _BYTES_PER_GIGABYTE,
            dataset_import_staging_directory=Path(
                _read_text(
                    "DATASET_IMPORT_STAGING_DIR", str(data_directory / "_imports")
                )
            ),
            dataset_conversion_python=_read_text("DATASET_CONVERSION_PYTHON", "")
            or None,
            maximum_dataset_download_bytes=(
                _read_integer("MAX_DATASET_DOWNLOAD_GB", 25) * _BYTES_PER_GIGABYTE
                or None
            ),
            tls_certificate_bundle=_read_text("TLS_CA_BUNDLE", "") or None,
            allow_insecure_downloads=_read_boolean("ALLOW_INSECURE_DOWNLOADS", False),
            simbu_r_script=Path(
                _read_text(
                    "SIMBU_R_SCRIPT", str(backend_root / "app" / "scripts" / "simbu.R")
                )
            ),
            simbu_task_timeout_seconds=_read_integer("SIMBU_TIMEOUT_SECONDS", 3600),
            h2o_max_memory=_read_text("H2O_MAX_MEMORY", "20g"),
            serve_bundled_frontend=_read_boolean("SERVE_FRONTEND", False),
            frontend_bundle_directory=Path(
                _read_text(
                    "FRONTEND_DIST", str(project_root / "frontend" / "dist")
                )
            ),
        )

    @property
    def user_workspaces_directory(self) -> Path:
        """Root directory below which every per-user workspace is created."""
        return self.data_directory / "users"

    @property
    def session_lifetime_seconds(self) -> int:
        return self.session_lifetime_hours * 3600


@lru_cache(maxsize=1)
def get_settings() -> ApplicationSettings:
    """Return the process-wide settings singleton."""
    return ApplicationSettings.from_environment()
