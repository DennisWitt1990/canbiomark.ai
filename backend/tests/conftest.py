"""Shared test fixtures.

The scientific stack (scanpy, h2o) is not needed for the tests below, and the
services import it lazily, so the whole API can be exercised without it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.application import create_application  # noqa: E402
from app.config.settings import ApplicationSettings  # noqa: E402

TEST_ADMIN_USERNAME = "admin"
TEST_ADMIN_PASSWORD = "initial-admin-1234"


@pytest.fixture()
def settings(tmp_path: Path) -> ApplicationSettings:
    """Settings pointing at a throwaway data directory."""
    data_directory = tmp_path / "data"
    return ApplicationSettings(
        data_directory=data_directory,
        database_file=data_directory / "test.sqlite",
        shared_input_directory=data_directory / "catalogue",
        session_cookie_name="canbiomark_session",
        session_lifetime_hours=1,
        session_cookie_secure=False,
        allowed_browser_origins=(),
        # Keep PBKDF2 cheap so the suite stays fast.
        password_hash_iterations=10_000,
        minimum_password_length=10,
        bootstrap_admin_username=TEST_ADMIN_USERNAME,
        bootstrap_admin_password=TEST_ADMIN_PASSWORD,
        bootstrap_admin_display_name="Administrator",
        default_user_quota_bytes=50 * 1024 * 1024 * 1024,
        dataset_import_staging_directory=data_directory / "_imports",
        dataset_conversion_python=None,
        maximum_dataset_download_bytes=1024 * 1024 * 1024,
        tls_certificate_bundle=None,
        allow_insecure_downloads=False,
        simbu_r_script=tmp_path / "simbu.R",
        simbu_task_timeout_seconds=60,
        h2o_max_memory="1g",
        serve_bundled_frontend=False,
        frontend_bundle_directory=tmp_path / "dist",
    )


@pytest.fixture()
def client(settings: ApplicationSettings) -> TestClient:
    """A test client whose cookie jar behaves like a browser's."""
    return TestClient(create_application(settings))


@pytest.fixture()
def admin_client(client: TestClient) -> TestClient:
    """A client already signed in as the bootstrap administrator."""
    response = client.post(
        "/api/auth/login",
        json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return client
