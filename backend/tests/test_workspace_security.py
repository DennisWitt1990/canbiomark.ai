"""The workspace must never hand out a path outside of itself."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.domain.errors import ValidationError, WorkspaceViolationError
from app.services.workspace_service import WorkspaceService
from tests.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME


@pytest.mark.parametrize(
    "malicious_path",
    [
        "../../../etc/passwd",
        "..",
        "/etc/passwd",
        "subdir/../../escape.txt",
        "C:\\Windows\\system32",
        "//server/share",
    ],
)
def test_traversal_attempts_are_refused(tmp_path: Path, malicious_path: str) -> None:
    workspace = WorkspaceService(tmp_path / "users").for_user("user-1")

    with pytest.raises((ValidationError, WorkspaceViolationError)):
        workspace.resolve(malicious_path, must_exist=False)


def test_a_legitimate_relative_path_resolves_inside_the_workspace(
    tmp_path: Path,
) -> None:
    workspace = WorkspaceService(tmp_path / "users").for_user("user-1")

    resolved = workspace.resolve("cell_selection/result.h5ad", must_exist=False)

    assert resolved.is_relative_to(workspace.root_directory)
    assert workspace.to_relative_path(resolved) == "cell_selection/result.h5ad"


def test_one_user_cannot_read_another_users_file(tmp_path: Path) -> None:
    workspace_service = WorkspaceService(tmp_path / "users")
    victim_workspace = workspace_service.for_user("victim")
    attacker_workspace = workspace_service.for_user("attacker")

    secret_file = victim_workspace.root_directory / "secret.txt"
    secret_file.write_text("confidential")

    with pytest.raises(WorkspaceViolationError):
        attacker_workspace.assert_inside(secret_file)


def test_the_download_endpoint_rejects_traversal(client: TestClient) -> None:
    client.post(
        "/api/auth/login",
        json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
    )

    response = client.get(
        "/api/workspace/download", params={"path": "../../../../etc/passwd"}
    )
    assert response.status_code in (400, 403)


def test_downloading_an_own_file_works(client: TestClient, settings) -> None:
    login = client.post(
        "/api/auth/login",
        json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
    )
    user_id = login.json()["user_id"]

    workspace = WorkspaceService(settings.user_workspaces_directory).for_user(user_id)
    (workspace.root_directory / "notes.txt").write_text("hello")

    response = client.get("/api/workspace/download", params={"path": "notes.txt"})
    assert response.status_code == 200
    assert response.text == "hello"
