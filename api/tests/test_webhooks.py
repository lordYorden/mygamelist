import socket
from datetime import datetime, timezone

from fastapi.testclient import TestClient
import httpx
import pytest

from app.database import get_db
from app.main import app
from app.models import Webhook
from app.webhooks import get_outbound_http_client


PASSWORD = "StrongerPass123!"


class FakeOutboundHttpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def post_json(self, url: str, payload: dict[str, object]) -> int:
        self.calls.append((url, payload))
        return 202


class FailingOutboundHttpClient:
    def post_json(self, url: str, payload: dict[str, object]) -> int:
        raise httpx.ConnectError("connection failed")


def register_payload(username: str) -> dict[str, str | bool]:
    return {
        "username": username,
        "email": f"{username}@example.com",
        "display_name": username.title(),
        "password": PASSWORD,
        "confirm_password": PASSWORD,
        "terms_accepted": True,
    }


def register_user(client: TestClient, username: str) -> dict:
    response = client.post("/api/register", json=register_payload(username))
    assert response.status_code == 201
    return response.json()


def token_for(client: TestClient, username: str) -> str:
    response = client.post("/api/auth/token", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200
    return response.json()["accessToken"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def fake_outbound() -> FakeOutboundHttpClient:
    outbound = FakeOutboundHttpClient()
    app.dependency_overrides[get_outbound_http_client] = lambda: outbound
    return outbound


@pytest.fixture(autouse=True)
def safe_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("8.8.8.8", 443))],
    )


def create_webhook(
    client: TestClient,
    token: str,
    url: str = "https://hooks.slack.com/services/test",
    title: str = "Slack alerts",
) -> dict:
    response = client.post("/api/webhooks", json={"title": title, "url": url}, headers=auth_header(token))
    assert response.status_code == 201
    return response.json()


def insert_webhook_record(client: TestClient, owner_user_id: str, url: str, title: str = "Legacy webhook") -> dict:
    db = next(app.dependency_overrides[get_db]())
    try:
        now = datetime.now(timezone.utc)
        webhook = Webhook(owner_user_id=owner_user_id, title=title, url=url, created_at=now, updated_at=now)
        db.add(webhook)
        db.commit()
        db.refresh(webhook)
        return {"id": webhook.id, "title": webhook.title, "url": webhook.url}
    finally:
        db.close()


def test_authenticated_user_can_register_webhook(client: TestClient, fake_outbound: FakeOutboundHttpClient) -> None:
    register_user(client, "alice")

    response = client.post(
        "/api/webhooks",
        json={"title": "Slack alerts", "url": "https://hooks.slack.com/services/test"},
        headers=auth_header(token_for(client, "alice")),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Slack alerts"
    assert body["url"] == "https://hooks.slack.com/services/test"
    assert "createdAt" in body
    assert fake_outbound.calls == []


@pytest.mark.parametrize(
    "url",
    [
        "https://attacker.example.com/collect",
        "http://hooks.slack.com/services/test",
        "https://169.254.169.254/latest/meta-data/",
    ],
)
def test_registering_blocked_urls_returns_422_without_saving(
    client: TestClient,
    fake_outbound: FakeOutboundHttpClient,
    url: str,
) -> None:
    register_user(client, "alice")
    token = token_for(client, "alice")

    response = client.post(
        "/api/webhooks",
        json={"title": "Unsafe target", "url": url},
        headers=auth_header(token),
    )

    assert response.status_code == 422
    assert client.get("/api/webhooks", headers=auth_header(token)).json() == []
    assert fake_outbound.calls == []


def test_unauthenticated_user_cannot_register_webhook(client: TestClient) -> None:
    response = client.post(
        "/api/webhooks",
        json={"title": "Slack alerts", "url": "https://hooks.slack.com/services/test"},
    )

    assert response.status_code == 401


def test_authenticated_user_lists_only_own_webhooks(
    client: TestClient,
    fake_outbound: FakeOutboundHttpClient,
) -> None:
    register_user(client, "alice")
    register_user(client, "bob")
    alice_token = token_for(client, "alice")
    bob_token = token_for(client, "bob")
    alice_webhook = create_webhook(client, alice_token)
    create_webhook(client, bob_token, "https://webhooks.discord.com/api/test")

    response = client.get("/api/webhooks", headers=auth_header(alice_token))

    assert response.status_code == 200
    assert [webhook["id"] for webhook in response.json()] == [alice_webhook["id"]]
    assert fake_outbound.calls == []


def test_owner_can_delete_webhook(client: TestClient, fake_outbound: FakeOutboundHttpClient) -> None:
    register_user(client, "alice")
    token = token_for(client, "alice")
    webhook = create_webhook(client, token)

    response = client.delete(f"/api/webhooks/{webhook['id']}", headers=auth_header(token))

    assert response.status_code == 204
    assert client.get("/api/webhooks", headers=auth_header(token)).json() == []
    assert fake_outbound.calls == []


def test_another_user_deleting_or_testing_webhook_gets_404(
    client: TestClient,
    fake_outbound: FakeOutboundHttpClient,
) -> None:
    register_user(client, "alice")
    register_user(client, "bob")
    webhook = create_webhook(client, token_for(client, "alice"))
    bob_header = auth_header(token_for(client, "bob"))

    delete_response = client.delete(f"/api/webhooks/{webhook['id']}", headers=bob_header)
    test_response = client.post(f"/api/webhooks/{webhook['id']}/test", headers=bob_header)

    assert delete_response.status_code == 404
    assert test_response.status_code == 404
    assert fake_outbound.calls == []


def test_testing_missing_webhook_returns_404(client: TestClient, fake_outbound: FakeOutboundHttpClient) -> None:
    register_user(client, "alice")

    response = client.post("/api/webhooks/missing/test", headers=auth_header(token_for(client, "alice")))

    assert response.status_code == 404
    assert fake_outbound.calls == []


@pytest.mark.parametrize(
    "url",
    [
        "https://attacker.example.com/collect",
        "http://hooks.slack.com/services/test",
        "https://169.254.169.254/latest/meta-data/",
    ],
)
def test_testing_blocked_urls_returns_422_without_calling_outbound_client(
    client: TestClient,
    fake_outbound: FakeOutboundHttpClient,
    url: str,
) -> None:
    user = register_user(client, "alice")
    token = token_for(client, "alice")
    webhook = insert_webhook_record(client, user["id"], url)

    response = client.post(f"/api/webhooks/{webhook['id']}/test", headers=auth_header(token))

    assert response.status_code == 422
    assert fake_outbound.calls == []


def test_testing_allowlisted_url_calls_outbound_client(
    client: TestClient,
    fake_outbound: FakeOutboundHttpClient,
) -> None:
    user = register_user(client, "alice")
    token = token_for(client, "alice")
    webhook = create_webhook(client, token)

    response = client.post(f"/api/webhooks/{webhook['id']}/test", headers=auth_header(token))

    assert response.status_code == 200
    assert response.json() == {"targetStatus": 202, "message": "Test notification delivered"}
    assert len(fake_outbound.calls) == 1
    url, payload = fake_outbound.calls[0]
    assert url == "https://hooks.slack.com/services/test"
    assert payload["event"] == "webhook.test"
    assert payload["notification"] == {
        "title": "MyGameList test notification",
        "body": "This test notification was sent to Slack alerts.",
        "actionType": "webhook.test",
        "actionMetadata": {
            "webhookId": webhook["id"],
            "webhookTitle": "Slack alerts",
        },
    }
    assert payload["user"] == {"id": user["id"], "username": "alice"}
    assert "sentAt" in payload


def test_testing_discord_webhook_sends_discord_payload(
    client: TestClient,
    fake_outbound: FakeOutboundHttpClient,
) -> None:
    register_user(client, "alice")
    token = token_for(client, "alice")
    webhook = create_webhook(
        client,
        token,
        url="https://discord.com/api/webhooks/test-token",
        title="Discord alerts",
    )

    response = client.post(f"/api/webhooks/{webhook['id']}/test", headers=auth_header(token))

    assert response.status_code == 200
    assert response.json() == {"targetStatus": 202, "message": "Test notification delivered"}
    assert len(fake_outbound.calls) == 1
    url, payload = fake_outbound.calls[0]
    assert url == "https://discord.com/api/webhooks/test-token"
    assert payload == {
        "content": "**MyGameList test notification**\nThis test notification was sent to Discord alerts.",
        "embeds": [
            {
                "title": "MyGameList test notification",
                "description": "This test notification was sent to Discord alerts.",
                "fields": [
                    {"name": "Event", "value": "webhook.test", "inline": True},
                ],
            }
        ],
        "allowed_mentions": {"parse": []},
    }


def test_testing_network_failure_returns_controlled_result(client: TestClient) -> None:
    app.dependency_overrides[get_outbound_http_client] = lambda: FailingOutboundHttpClient()
    register_user(client, "alice")
    token = token_for(client, "alice")
    webhook = create_webhook(client, token)

    response = client.post(f"/api/webhooks/{webhook['id']}/test", headers=auth_header(token))

    assert response.status_code == 200
    assert response.json() == {"targetStatus": None, "message": "Webhook delivery failed"}


def test_delete_game_entry_triggers_deleted_event_for_user_webhooks(
    client: TestClient,
    fake_outbound: FakeOutboundHttpClient,
) -> None:
    user = register_user(client, "alice")
    token = token_for(client, "alice")
    create_webhook(client, token)

    response = client.delete("/api/game-entries/entry-123", headers=auth_header(token))

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert fake_outbound.calls == [
        (
            "https://hooks.slack.com/services/test",
            {
                "event": "game_entry.deleted",
                "entryId": "entry-123",
                "userId": user["id"],
                "username": "alice",
            },
        )
    ]
