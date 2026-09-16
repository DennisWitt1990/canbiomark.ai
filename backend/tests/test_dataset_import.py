"""Dataset import: access control, naming and the cell-type pause."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.domain.dataset_import import DatasetImportJob, ImportStage
from app.domain.errors import ValidationError
from tests.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME

import pytest


# --- catalogue naming -------------------------------------------------------


@pytest.mark.parametrize(
    ("raw_name", "expected"),
    [
        ("Liver Atlas", "liver_atlas"),
        ("  gondal2025  ", "gondal2025"),
        ("../../escape", "escape"),
        ("a/b/c", "a_b_c"),
        ("UPPER_case-1", "upper_case-1"),
    ],
)
def test_catalogue_names_are_reduced_to_a_safe_token(raw_name, expected) -> None:
    assert DatasetImportJob.sanitize_catalogue_name(raw_name) == expected


@pytest.mark.parametrize("raw_name", ["", "   ", "///", "..."])
def test_an_empty_catalogue_name_is_refused(raw_name) -> None:
    with pytest.raises(ValidationError):
        DatasetImportJob.sanitize_catalogue_name(raw_name)


def test_a_long_catalogue_name_is_truncated() -> None:
    result = DatasetImportJob.sanitize_catalogue_name("x" * 200)
    assert len(result) <= 48


# --- import stages ----------------------------------------------------------


def test_the_waiting_stage_is_the_only_one_needing_input() -> None:
    needing_input = [stage for stage in ImportStage if stage.needs_user_input]
    assert needing_input == [ImportStage.AWAITING_CELL_TYPE_COLUMN]


def test_terminal_stages_are_marked_as_such() -> None:
    assert ImportStage.FINISHED.is_terminal
    assert ImportStage.FAILED.is_terminal
    assert ImportStage.CANCELLED.is_terminal
    assert not ImportStage.DOWNLOADING.is_terminal
    assert not ImportStage.AWAITING_CELL_TYPE_COLUMN.is_terminal


# --- access control ---------------------------------------------------------


def test_the_importer_requires_a_session(client: TestClient) -> None:
    assert client.post("/api/dataset-import/search", json={}).status_code == 401
    assert client.get("/api/dataset-import/jobs").status_code == 401


def test_a_researcher_cannot_import_datasets(client: TestClient) -> None:
    """Importing writes into the shared catalogue, so it is administrator only."""
    client.post(
        "/api/auth/login",
        json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
    )
    client.post(
        "/api/admin/users",
        json={
            "username": "researcher",
            "role": "researcher",
            "initial_password": "researcher-pw-12",
            "require_password_change": False,
        },
    )
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/login",
        json={"username": "researcher", "password": "researcher-pw-12"},
    )

    assert client.post("/api/dataset-import/search", json={}).status_code == 403
    assert client.get("/api/dataset-import/jobs").status_code == 403
    assert (
        client.post(
            "/api/dataset-import/jobs",
            json={"dataset": {}, "catalogue_name": "x"},
        ).status_code
        == 403
    )


def test_an_administrator_sees_an_empty_import_list(admin_client: TestClient) -> None:
    response = admin_client.get("/api/dataset-import/jobs")
    assert response.status_code == 200
    assert response.json() == []


def test_a_free_text_query_against_ebi_is_refused_with_guidance(
    admin_client: TestClient,
) -> None:
    """BioStudies free-text search returns publications, not datasets."""
    response = admin_client.post(
        "/api/dataset-import/search",
        json={"source": "ebi_biostudies", "query": "single cell liver"},
    )
    assert response.status_code == 400
    assert "accession" in response.json()["detail"].lower()


def test_an_unknown_source_is_rejected(admin_client: TestClient) -> None:
    response = admin_client.post(
        "/api/dataset-import/search", json={"source": "sketchy_source", "query": "x"}
    )
    assert response.status_code == 400
    assert "sketchy_source" in response.json()["detail"]


def test_an_unknown_import_job_is_reported_as_missing(admin_client: TestClient) -> None:
    response = admin_client.get("/api/dataset-import/jobs/does-not-exist")
    assert response.status_code == 404
