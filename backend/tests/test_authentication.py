"""End-to-end tests of the password based authentication."""
from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME


def test_bootstrap_administrator_can_sign_in(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == TEST_ADMIN_USERNAME
    assert body["is_administrator"] is True
    assert "canbiomark_session" in response.cookies


def test_username_is_case_insensitive(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": TEST_ADMIN_USERNAME.upper(), "password": TEST_ADMIN_PASSWORD},
    )
    assert response.status_code == 200


def test_wrong_password_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": TEST_ADMIN_USERNAME, "password": "definitely-wrong-1"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Username or password is incorrect."


def test_unknown_user_gives_the_same_message_as_a_wrong_password(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "nobody", "password": "definitely-wrong-1"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Username or password is incorrect."


def test_protected_endpoint_requires_a_session(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/cell-selection/experiments").status_code == 401
    assert client.get("/api/admin/users").status_code == 401


def test_logout_invalidates_the_session(admin_client: TestClient) -> None:
    assert admin_client.get("/api/auth/me").status_code == 200

    assert admin_client.post("/api/auth/logout").status_code == 200

    assert admin_client.get("/api/auth/me").status_code == 401


def test_health_endpoint_needs_no_session(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_changing_the_own_password_signs_every_session_out(
    admin_client: TestClient,
) -> None:
    response = admin_client.post(
        "/api/auth/change-password",
        json={
            "current_password": TEST_ADMIN_PASSWORD,
            "new_password": "a-brand-new-password-9",
        },
    )
    assert response.status_code == 200
    assert admin_client.get("/api/auth/me").status_code == 401

    # The old password no longer works, the new one does.
    assert (
        admin_client.post(
            "/api/auth/login",
            json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
        ).status_code
        == 401
    )
    assert (
        admin_client.post(
            "/api/auth/login",
            json={
                "username": TEST_ADMIN_USERNAME,
                "password": "a-brand-new-password-9",
            },
        ).status_code
        == 200
    )


def test_weak_passwords_are_rejected(admin_client: TestClient) -> None:
    response = admin_client.post(
        "/api/auth/change-password",
        json={"current_password": TEST_ADMIN_PASSWORD, "new_password": "short1"},
    )
    assert response.status_code == 400
    assert "at least 10 characters" in response.json()["detail"]
