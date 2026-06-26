from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image


def register_and_login(client: TestClient) -> str:
    client.post(
        "/api/register",
        json={
            "username": "alice",
            "email": "alice@example.com",
            "display_name": "Alice",
            "password": "StrongerPass123!",
            "confirm_password": "StrongerPass123!",
            "terms_accepted": True,
        },
    )
    token_response = client.post(
        "/api/auth/token",
        json={"username": "alice", "password": "StrongerPass123!"},
    )
    return token_response.json()["accessToken"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (1, 1), color=(12, 34, 56)).save(output, format="PNG")
    return output.getvalue()


def test_profile_picture_upload_stores_metadata_and_updates_user(client: TestClient, monkeypatch) -> None:
    stored_objects: dict[tuple[str, str], dict] = {}

    class FakeS3Client:
        def put_object(self, **kwargs):
            stored_objects[(kwargs["Bucket"], kwargs["Key"])] = kwargs

        def get_object(self, Bucket: str, Key: str):
            stored = stored_objects[(Bucket, Key)]
            return {"Body": BytesIO(stored["Body"]), "ContentType": stored["ContentType"]}

    monkeypatch.setattr("app.uploads.get_s3_client", lambda settings: FakeS3Client())
    token = register_and_login(client)

    response = client.post(
        "/api/me/profile-picture",
        headers=auth_headers(token),
        files={"file": ("avatar.png", png_bytes(), "image/png")},
    )

    assert response.status_code == 200
    assert response.json()["profilePictureUrl"] == "/api/me/profile-picture"

    picture = client.get("/api/me/profile-picture", headers=auth_headers(token))
    assert picture.status_code == 200
    assert picture.headers["content-type"].startswith("image/png")
    assert picture.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_profile_picture_upload_requires_authentication(client: TestClient) -> None:
    response = client.post(
        "/api/me/profile-picture",
        files={"file": ("avatar.png", png_bytes(), "image/png")},
    )

    assert response.status_code == 401


def test_profile_picture_upload_rejects_bad_magic_bytes(client: TestClient) -> None:
    token = register_and_login(client)

    response = client.post(
        "/api/me/profile-picture",
        headers=auth_headers(token),
        files={"file": ("avatar.png", b"not really an image", "image/png")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Upload rejected"


def test_profile_picture_upload_rejects_large_files(client: TestClient) -> None:
    token = register_and_login(client)
    oversized = b"\x89PNG\r\n\x1a\n" + (b"x" * (2 * 1024 * 1024))

    response = client.post(
        "/api/me/profile-picture",
        headers=auth_headers(token),
        files={"file": ("avatar.png", oversized, "image/png")},
    )

    assert response.status_code == 413


def test_profile_picture_upload_rate_limits_repeated_attempts(client: TestClient, monkeypatch) -> None:
    class FakeS3Client:
        def put_object(self, **kwargs):
            return None

    monkeypatch.setattr("app.uploads.get_s3_client", lambda settings: FakeS3Client())
    token = register_and_login(client)

    for _ in range(10):
        response = client.post(
            "/api/me/profile-picture",
            headers=auth_headers(token),
            files={"file": ("avatar.png", png_bytes(), "image/png")},
        )
        assert response.status_code == 200

    limited = client.post(
        "/api/me/profile-picture",
        headers=auth_headers(token),
        files={"file": ("avatar.png", png_bytes(), "image/png")},
    )
    assert limited.status_code == 429
