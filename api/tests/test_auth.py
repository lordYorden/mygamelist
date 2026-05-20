import os
from collections.abc import Generator

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["JWT_SECRET"] = "test-secret-with-enough-entropy"

from app.config import get_settings  # noqa: E402
from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    get_settings.cache_clear()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    SQLModel.metadata.drop_all(bind=engine)


def register_payload(username: str, email: str) -> dict[str, str | bool]:
    return {
        "username": username,
        "email": email,
        "display_name": username.title(),
        "password": "StrongerPass123!",
        "confirm_password": "StrongerPass123!",
        "terms_accepted": True,
        "role": "ADMIN",
    }


def test_register_bootstraps_first_admin_and_prevents_hash_exposure(client: TestClient) -> None:
    first = client.post("/api/register", json=register_payload("alice", "alice@example.com"))
    assert first.status_code == 201
    body = first.json()
    assert body["role"] == "ADMIN"
    assert "password_hash" not in body
    assert "passwordHash" not in body

    second = client.post("/api/register", json=register_payload("bob", "bob@example.com"))
    assert second.status_code == 201
    assert second.json()["role"] == "GAMER"


def test_password_is_argon2i_hash(client: TestClient) -> None:
    client.post("/api/register", json=register_payload("alice", "alice@example.com"))

    db = next(app.dependency_overrides[get_db]())
    try:
        stored_hash = db.exec(select(User.password_hash).where(User.username == "alice")).one()
    finally:
        db.close()

    assert stored_hash.startswith("$argon2i$")
    assert "StrongerPass123!" not in stored_hash


def test_login_and_me_with_bearer_token(client: TestClient) -> None:
    client.post("/api/register", json=register_payload("alice", "alice@example.com"))
    token_response = client.post(
        "/api/auth/token",
        json={"username": "alice", "password": "StrongerPass123!"},
    )
    assert token_response.status_code == 200
    assert set(token_response.json()) == {"accessToken", "tokenType", "expiresIn"}

    me = client.get("/api/me", headers={"Authorization": f"Bearer {token_response.json()['accessToken']}"})
    assert me.status_code == 200
    assert me.json()["username"] == "alice"
    assert "password_hash" not in me.json()


def test_rejects_missing_wrong_tampered_and_alg_none_tokens(client: TestClient) -> None:
    client.post("/api/register", json=register_payload("alice", "alice@example.com"))

    assert client.get("/api/me").status_code == 401
    assert client.post("/api/auth/token", json={"username": "alice", "password": "wrong"}).status_code == 401

    token = client.post(
        "/api/auth/token",
        json={"username": "alice", "password": "StrongerPass123!"},
    ).json()["accessToken"]
    tampered = token[:-3] + "abc"
    assert client.get("/api/me", headers={"Authorization": f"Bearer {tampered}"}).status_code == 401

    alg_none = jwt.encode(
        {"sub": "alice", "user_id": "fake", "role": "ADMIN", "iss": "mygamelist-api", "iat": 1, "exp": 9999999999},
        key="",
        algorithm="none",
    )
    assert client.get("/api/me", headers={"Authorization": f"Bearer {alg_none}"}).status_code == 401
