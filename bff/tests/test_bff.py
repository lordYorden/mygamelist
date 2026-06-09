from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.sessions import session_store


class FakeAsyncClient:
    proxied_requests: list[tuple[str, str]] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, *args) -> None:
        return None

    async def post(self, path: str, json: dict) -> httpx.Response:
        if path == "/api/auth/token" and json["password"] == "StrongerPass123!":
            return httpx.Response(200, json={"accessToken": "api.jwt.token", "expiresIn": 1800, "tokenType": "Bearer"})
        return httpx.Response(401, json={"detail": "Invalid credentials"})

    async def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        self.proxied_requests.append((method, path))
        if method == "POST" and path == "/api/register":
            return httpx.Response(
                201,
                json={"id": "user-3", "username": "cara", "email": "cara@example.com", "role": "GAMER"},
            )
        if kwargs["headers"].get("Authorization") == "Bearer api.jwt.token":
            if method == "PATCH" and path == "/api/admin/users/user-2/role":
                return httpx.Response(200, json={"id": "user-2", "username": "bob", "role": "MODERATOR"})
            return httpx.Response(200, json={"username": "alice", "role": "ADMIN"})
        return httpx.Response(401, json={"detail": "Not authenticated"})


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    app.dependency_overrides[get_settings] = lambda: Settings(api_base_url="http://api.test", cookie_secure=False)
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    FakeAsyncClient.proxied_requests.clear()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    session_store._sessions.clear()
    FakeAsyncClient.proxied_requests.clear()


def csrf_headers(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("XSRF-TOKEN")
    assert token is not None
    return {"X-XSRF-TOKEN": token}


def login(client: TestClient) -> None:
    client.get("/health")
    response = client.post(
        "/login",
        data={
            "username": "alice",
            "password": "StrongerPass123!",
            "_csrf": client.cookies.get("XSRF-TOKEN"),
        },
    )
    assert response.status_code == 200


def test_safe_request_issues_csrf_cookie(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert "XSRF-TOKEN=" in cookie
    assert "HttpOnly" not in cookie
    assert "SameSite=strict" in cookie


def test_login_sets_http_only_bff_session_without_exposing_jwt(client: TestClient) -> None:
    client.get("/health")
    response = client.post(
        "/login",
        data={
            "username": "alice",
            "password": "StrongerPass123!",
            "_csrf": client.cookies.get("XSRF-TOKEN"),
        },
    )

    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "Logged in"}
    assert "accessToken" not in response.text
    cookie = response.headers["set-cookie"]
    assert "BFF-SESSION=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie


def test_proxy_requires_session_then_adds_bearer_token(client: TestClient) -> None:
    assert client.get("/api/me").status_code == 401

    login(client)
    response = client.get("/api/me")

    assert response.status_code == 200
    assert response.json()["username"] == "alice"


def test_proxy_forwards_admin_patch_with_session_token(client: TestClient) -> None:
    login(client)

    response = client.patch(
        "/api/admin/users/user-2/role",
        json={"role": "MODERATOR"},
        headers=csrf_headers(client),
    )

    assert response.status_code == 200
    assert response.json() == {"id": "user-2", "username": "bob", "role": "MODERATOR"}


def test_logout_clears_session(client: TestClient) -> None:
    login(client)

    logout = client.post("/logout", headers=csrf_headers(client))
    assert logout.status_code == 200
    assert "BFF-SESSION=" in logout.headers["set-cookie"]

    assert client.get("/api/me").status_code == 401


def test_login_rejects_missing_csrf_token(client: TestClient) -> None:
    response = client.post("/login", data={"username": "alice", "password": "StrongerPass123!"})

    assert response.status_code == 403
    assert response.json() == {"detail": "CSRF token missing or invalid"}
    assert client.cookies.get("BFF-SESSION") is None


def test_login_rejects_wrong_csrf_token(client: TestClient) -> None:
    client.get("/health")

    response = client.post(
        "/login",
        data={"username": "alice", "password": "StrongerPass123!", "_csrf": "wrong-token"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "CSRF token missing or invalid"}
    assert client.cookies.get("BFF-SESSION") is None


def test_logout_rejects_missing_csrf_token(client: TestClient) -> None:
    login(client)
    client.cookies.delete("XSRF-TOKEN")

    logout = client.post("/logout")

    assert logout.status_code == 403
    assert logout.json() == {"detail": "CSRF token missing or invalid"}
    assert client.get("/api/me").status_code == 200


def test_admin_patch_rejects_missing_csrf_token(client: TestClient) -> None:
    login(client)
    FakeAsyncClient.proxied_requests.clear()
    client.cookies.delete("XSRF-TOKEN")

    response = client.patch("/api/admin/users/user-2/role", json={"role": "MODERATOR"})

    assert response.status_code == 403
    assert response.json() == {"detail": "CSRF token missing or invalid"}
    assert FakeAsyncClient.proxied_requests == []


def test_admin_patch_rejects_wrong_csrf_token(client: TestClient) -> None:
    login(client)
    FakeAsyncClient.proxied_requests.clear()

    response = client.patch(
        "/api/admin/users/user-2/role",
        json={"role": "MODERATOR"},
        headers={"X-XSRF-TOKEN": "wrong-token"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "CSRF token missing or invalid"}
    assert FakeAsyncClient.proxied_requests == []


def test_register_rejects_missing_csrf_token(client: TestClient) -> None:
    response = client.post(
        "/api/register",
        json={"username": "cara", "email": "cara@example.com", "password": "StrongerPass123!"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "CSRF token missing or invalid"}
    assert FakeAsyncClient.proxied_requests == []


def test_register_allows_valid_csrf_without_session(client: TestClient) -> None:
    client.get("/health")

    response = client.post(
        "/api/register",
        json={"username": "cara", "email": "cara@example.com", "password": "StrongerPass123!"},
        headers=csrf_headers(client),
    )

    assert response.status_code == 201
    assert response.json()["username"] == "cara"
    assert FakeAsyncClient.proxied_requests == [("POST", "/api/register")]
