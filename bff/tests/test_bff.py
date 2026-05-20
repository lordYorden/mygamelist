from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.sessions import session_store


class FakeAsyncClient:
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
        if kwargs["headers"].get("Authorization") == "Bearer api.jwt.token":
            return httpx.Response(200, json={"username": "alice", "role": "ADMIN"})
        return httpx.Response(401, json={"detail": "Not authenticated"})


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    app.dependency_overrides[get_settings] = lambda: Settings(api_base_url="http://api.test", cookie_secure=False)
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    session_store._sessions.clear()


def test_login_sets_http_only_bff_session_without_exposing_jwt(client: TestClient) -> None:
    response = client.post("/login", data={"username": "alice", "password": "StrongerPass123!"})

    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "Logged in"}
    assert "accessToken" not in response.text
    cookie = response.headers["set-cookie"]
    assert "BFF-SESSION=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie


def test_proxy_requires_session_then_adds_bearer_token(client: TestClient) -> None:
    assert client.get("/api/me").status_code == 401

    client.post("/login", data={"username": "alice", "password": "StrongerPass123!"})
    response = client.get("/api/me")

    assert response.status_code == 200
    assert response.json()["username"] == "alice"


def test_logout_clears_session(client: TestClient) -> None:
    client.post("/login", data={"username": "alice", "password": "StrongerPass123!"})

    logout = client.post("/logout")
    assert logout.status_code == 200
    assert "BFF-SESSION=" in logout.headers["set-cookie"]

    assert client.get("/api/me").status_code == 401
