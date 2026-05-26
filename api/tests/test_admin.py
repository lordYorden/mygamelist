from fastapi.testclient import TestClient

from app.models import UserRole


PASSWORD = "StrongerPass123!"


def register_payload(username: str, email: str) -> dict[str, str | bool]:
    return {
        "username": username,
        "email": email,
        "display_name": username.title(),
        "password": PASSWORD,
        "confirm_password": PASSWORD,
        "terms_accepted": True,
    }


def register_user(client: TestClient, username: str, role: UserRole | None = None) -> dict:
    response = client.post("/api/register", json=register_payload(username, f"{username}@example.com"))
    assert response.status_code == 201
    body = response.json()
    if role is not None:
        token = token_for(client, "alice")
        update = client.patch(
            f"/api/admin/users/{body['id']}/role",
            json={"role": role.value},
            headers=auth_header(token),
        )
        assert update.status_code == 200
        body = update.json()
    return body


def token_for(client: TestClient, username: str) -> str:
    response = client.post("/api/auth/token", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200
    return response.json()["accessToken"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_admin_can_list_users_without_sensitive_fields(client: TestClient) -> None:
    register_user(client, "alice")
    register_user(client, "bob")

    response = client.get("/api/admin/users", headers=auth_header(token_for(client, "alice")))

    assert response.status_code == 200
    users = response.json()
    assert [user["username"] for user in users] == ["alice", "bob"]
    assert all("password_hash" not in user for user in users)
    assert all("passwordHash" not in user for user in users)


def test_non_admins_cannot_list_users(client: TestClient) -> None:
    register_user(client, "alice")
    register_user(client, "bob")
    register_user(client, "mara", UserRole.MODERATOR)

    gamer_response = client.get("/api/admin/users", headers=auth_header(token_for(client, "bob")))
    moderator_response = client.get("/api/admin/users", headers=auth_header(token_for(client, "mara")))

    assert gamer_response.status_code == 403
    assert moderator_response.status_code == 403


def test_unauthenticated_user_cannot_list_users(client: TestClient) -> None:
    response = client.get("/api/admin/users")

    assert response.status_code == 401


def test_admin_can_change_another_users_role(client: TestClient) -> None:
    register_user(client, "alice")
    bob = register_user(client, "bob")

    response = client.patch(
        f"/api/admin/users/{bob['id']}/role",
        json={"role": "MODERATOR"},
        headers=auth_header(token_for(client, "alice")),
    )

    assert response.status_code == 200
    assert response.json()["role"] == "MODERATOR"
    assert "password_hash" not in response.json()
    assert "passwordHash" not in response.json()


def test_admin_cannot_change_own_role(client: TestClient) -> None:
    alice = register_user(client, "alice")

    response = client.patch(
        f"/api/admin/users/{alice['id']}/role",
        json={"role": "GAMER"},
        headers=auth_header(token_for(client, "alice")),
    )

    assert response.status_code == 409


def test_non_admin_cannot_change_any_role(client: TestClient) -> None:
    register_user(client, "alice")
    bob = register_user(client, "bob")

    response = client.patch(
        f"/api/admin/users/{bob['id']}/role",
        json={"role": "ADMIN"},
        headers=auth_header(token_for(client, "bob")),
    )

    assert response.status_code == 403


def test_admin_gets_404_when_changing_missing_user(client: TestClient) -> None:
    register_user(client, "alice")

    response = client.patch(
        "/api/admin/users/missing-user/role",
        json={"role": "GAMER"},
        headers=auth_header(token_for(client, "alice")),
    )

    assert response.status_code == 404
