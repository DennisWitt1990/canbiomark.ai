"""Tests of the administrator's user management."""
from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME


def create_researcher(
    admin_client: TestClient, username: str = "researcher", **overrides
) -> dict:
    payload = {
        "username": username,
        "display_name": "Test Researcher",
        "role": "researcher",
        "quota_gigabytes": 10,
        "require_password_change": False,
        **overrides,
    }
    response = admin_client.post("/api/admin/users", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_administrator_creates_an_account_with_a_generated_password(
    admin_client: TestClient,
) -> None:
    created = create_researcher(admin_client)

    assert created["user"]["username"] == "researcher"
    assert created["user"]["role"] == "researcher"
    assert created["user"]["quota_gigabytes"] == 10.0
    # The generated password is returned exactly once.
    assert len(created["initial_password"]) >= 10


def test_a_created_account_can_sign_in(client: TestClient) -> None:
    client.post(
        "/api/auth/login",
        json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
    )
    created = create_researcher(client, initial_password="researcher-pw-12")
    client.post("/api/auth/logout")

    response = client.post(
        "/api/auth/login",
        json={"username": "researcher", "password": "researcher-pw-12"},
    )
    assert response.status_code == 200
    assert response.json()["is_administrator"] is False
    assert created["user"]["user_id"] == response.json()["user_id"]


def test_a_researcher_cannot_reach_the_administration_endpoints(
    client: TestClient,
) -> None:
    client.post(
        "/api/auth/login",
        json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
    )
    create_researcher(client, initial_password="researcher-pw-12")
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/login",
        json={"username": "researcher", "password": "researcher-pw-12"},
    )

    assert client.get("/api/admin/users").status_code == 403
    assert client.post("/api/admin/users", json={"username": "x2y"}).status_code == 403


def test_duplicate_usernames_are_rejected(admin_client: TestClient) -> None:
    create_researcher(admin_client)
    response = admin_client.post(
        "/api/admin/users",
        json={"username": "RESEARCHER", "role": "researcher"},
    )
    assert response.status_code == 400
    assert "already taken" in response.json()["detail"]


def test_disabling_an_account_revokes_its_sessions(client: TestClient) -> None:
    client.post(
        "/api/auth/login",
        json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
    )
    created = create_researcher(client, initial_password="researcher-pw-12")
    user_id = created["user"]["user_id"]
    client.post("/api/auth/logout")

    # The researcher signs in on their own client.
    researcher_client = TestClient(client.app)
    assert (
        researcher_client.post(
            "/api/auth/login",
            json={"username": "researcher", "password": "researcher-pw-12"},
        ).status_code
        == 200
    )
    assert researcher_client.get("/api/auth/me").status_code == 200

    # The administrator disables the account.
    client.post(
        "/api/auth/login",
        json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
    )
    assert (
        client.patch(f"/api/admin/users/{user_id}", json={"is_active": False}).status_code
        == 200
    )

    # The running session stops working immediately.
    assert researcher_client.get("/api/auth/me").status_code == 401
    assert (
        researcher_client.post(
            "/api/auth/login",
            json={"username": "researcher", "password": "researcher-pw-12"},
        ).status_code
        == 403
    )


def test_resetting_a_password_returns_it_once_and_invalidates_the_old_one(
    client: TestClient,
) -> None:
    client.post(
        "/api/auth/login",
        json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
    )
    created = create_researcher(client, initial_password="researcher-pw-12")
    user_id = created["user"]["user_id"]

    response = client.post(f"/api/admin/users/{user_id}/password", json={})
    assert response.status_code == 200
    new_password = response.json()["new_password"]
    assert new_password != "researcher-pw-12"

    client.post("/api/auth/logout")
    assert (
        client.post(
            "/api/auth/login",
            json={"username": "researcher", "password": "researcher-pw-12"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login",
            json={"username": "researcher", "password": new_password},
        ).status_code
        == 200
    )


def test_quota_and_role_can_be_changed(admin_client: TestClient) -> None:
    created = create_researcher(admin_client)
    user_id = created["user"]["user_id"]

    response = admin_client.patch(
        f"/api/admin/users/{user_id}",
        json={"quota_gigabytes": 200, "role": "administrator", "display_name": "Renamed"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["quota_gigabytes"] == 200.0
    assert body["role"] == "administrator"
    assert body["display_name"] == "Renamed"


def test_the_last_administrator_cannot_be_disabled_or_deleted(
    admin_client: TestClient,
) -> None:
    users = admin_client.get("/api/admin/users").json()["users"]
    administrator = next(user for user in users if user["role"] == "administrator")
    admin_id = administrator["user_id"]

    disable_response = admin_client.patch(
        f"/api/admin/users/{admin_id}", json={"is_active": False}
    )
    assert disable_response.status_code == 400
    assert "last active administrator" in disable_response.json()["detail"]

    delete_response = admin_client.delete(f"/api/admin/users/{admin_id}")
    assert delete_response.status_code == 400


def test_deleting_an_account_removes_it_from_the_list(admin_client: TestClient) -> None:
    created = create_researcher(admin_client)
    user_id = created["user"]["user_id"]

    assert admin_client.delete(f"/api/admin/users/{user_id}").status_code == 200

    usernames = [
        user["username"] for user in admin_client.get("/api/admin/users").json()["users"]
    ]
    assert "researcher" not in usernames


def test_sessions_can_be_listed_and_revoked(client: TestClient) -> None:
    client.post(
        "/api/auth/login",
        json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
    )
    created = create_researcher(client, initial_password="researcher-pw-12")
    user_id = created["user"]["user_id"]

    researcher_client = TestClient(client.app)
    researcher_client.post(
        "/api/auth/login",
        json={"username": "researcher", "password": "researcher-pw-12"},
    )

    sessions = client.get(f"/api/admin/users/{user_id}/sessions").json()
    assert len(sessions) == 1
    # Only a preview of the id is exposed, never the full session hash.
    assert len(sessions[0]["session_id_preview"]) == 12

    revoked = client.delete(f"/api/admin/users/{user_id}/sessions").json()
    assert revoked["revoked_session_count"] == 1
    assert researcher_client.get("/api/auth/me").status_code == 401


def test_administrative_actions_are_written_to_the_audit_trail(
    admin_client: TestClient,
) -> None:
    create_researcher(admin_client)

    events = admin_client.get("/api/admin/audit").json()
    actions = {event["action"] for event in events}
    assert "user.created" in actions
    assert "login.succeeded" in actions


def test_an_unknown_role_is_reported_clearly(admin_client: TestClient) -> None:
    """A bad enum value must give a 400 that names it, not an opaque 500."""
    response = admin_client.post(
        "/api/admin/users", json={"username": "someone", "role": "wizard"}
    )
    assert response.status_code == 400
    assert "wizard" in response.json()["detail"]
    assert "researcher" in response.json()["detail"]
