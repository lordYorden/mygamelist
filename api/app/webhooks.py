import logging
from datetime import datetime, timezone
from typing import Annotated
from urllib.parse import urlsplit

import httpx
from fastapi import Depends, HTTPException, status
from sqlmodel import Session, select

from .config import Settings, get_settings
from .models import User, Webhook
from .schemas import WebhookRequest, WebhookTestResult
from .ssrf import BlockedUrlError, SsrfGuard

logger = logging.getLogger(__name__)


class OutboundHttpClient:
    def __init__(self, settings: Settings) -> None:
        self.timeout = httpx.Timeout(
            connect=settings.webhook_connect_timeout_seconds,
            read=settings.webhook_read_timeout_seconds,
            write=settings.webhook_read_timeout_seconds,
            pool=settings.webhook_connect_timeout_seconds,
        )

    def post_json(self, url: str, payload: dict[str, object]) -> int:
        with httpx.Client(follow_redirects=False, timeout=self.timeout) as client:
            response = client.post(url, json=payload)
        return response.status_code


class WebhookService:
    def __init__(self, ssrf_guard: SsrfGuard, outbound_http_client: OutboundHttpClient) -> None:
        self.ssrf_guard = ssrf_guard
        self.outbound_http_client = outbound_http_client

    def create_webhook(self, db: Session, user: User, request: WebhookRequest) -> Webhook:
        self.ssrf_guard.validate(request.url)
        now = datetime.now(timezone.utc)
        webhook = Webhook(owner_user_id=user.id, title=request.title, url=request.url, created_at=now, updated_at=now)
        db.add(webhook)
        db.commit()
        db.refresh(webhook)
        return webhook

    def list_webhooks(self, db: Session, user: User) -> list[Webhook]:
        return list(
            db.exec(
                select(Webhook)
                .where(Webhook.owner_user_id == user.id)
                .order_by(Webhook.created_at.desc(), Webhook.id)
            ).all()
        )

    def delete_webhook(self, db: Session, user: User, webhook_id: str) -> None:
        webhook = self._get_owned_webhook(db, user, webhook_id)
        db.delete(webhook)
        db.commit()

    def test_webhook(self, db: Session, user: User, webhook_id: str) -> WebhookTestResult:
        webhook = self._get_owned_webhook(db, user, webhook_id)
        payload = self._test_notification_payload(webhook, user)
        try:
            target_status = self._deliver(webhook.url, payload)
        except BlockedUrlError:
            raise
        except httpx.HTTPError:
            logger.info("webhook_test_delivery_failed user_id=%s webhook_id=%s", user.id, webhook.id, exc_info=True)
            return WebhookTestResult(target_status=None, message="Webhook delivery failed")
        return WebhookTestResult(target_status=target_status, message="Test notification delivered")

    def send_event(self, db: Session, user: User, event_type: str, payload: dict[str, object]) -> None:
        for webhook in self.list_webhooks(db, user):
            event_payload = self._event_payload_for_webhook(webhook, user, event_type, payload)
            try:
                self._deliver(webhook.url, event_payload)
            except Exception:
                logger.info(
                    "webhook_event_delivery_failed user_id=%s webhook_id=%s event=%s",
                    user.id,
                    webhook.id,
                    event_type,
                    exc_info=True,
                )

    def _deliver(self, url: str, payload: dict[str, object]) -> int:
        self.ssrf_guard.validate(url)
        return self.outbound_http_client.post_json(url, payload)

    def _test_notification_payload(self, webhook: Webhook, user: User) -> dict[str, object]:
        sent_at = datetime.now(timezone.utc).isoformat()
        generic_payload = {
            "event": "webhook.test",
            "notification": {
                "title": "MyGameList test notification",
                "body": f"This test notification was sent to {webhook.title}.",
                "actionType": "webhook.test",
                "actionMetadata": {
                    "webhookId": webhook.id,
                    "webhookTitle": webhook.title,
                },
            },
            "user": {
                "id": user.id,
                "username": user.username,
            },
            "sentAt": sent_at,
        }
        return self._payload_for_webhook_url(webhook.url, generic_payload)

    def _event_payload_for_webhook(
        self,
        webhook: Webhook,
        user: User,
        event_type: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        generic_payload = {"event": event_type, **payload}
        return self._payload_for_webhook_url(webhook.url, generic_payload)

    def _payload_for_webhook_url(self, url: str, generic_payload: dict[str, object]) -> dict[str, object]:
        host = (urlsplit(url).hostname or "").lower().rstrip(".")
        if host == "discord.com" or host.endswith(".discord.com"):
            return self._discord_payload(generic_payload)
        return generic_payload

    def _discord_payload(self, generic_payload: dict[str, object]) -> dict[str, object]:
        event = str(generic_payload.get("event", "mygamelist.event"))
        notification = generic_payload.get("notification")
        title = "MyGameList notification"
        body = f"Event: {event}"

        if isinstance(notification, dict):
            title = str(notification.get("title") or title)
            body = str(notification.get("body") or body)
        elif event == "game_entry.deleted":
            title = "Game entry deleted"
            body = f"Entry {generic_payload.get('entryId', 'unknown')} was deleted."

        return {
            "content": f"**{title}**\n{body}",
            "embeds": [
                {
                    "title": title,
                    "description": body,
                    "fields": [
                        {"name": "Event", "value": event, "inline": True},
                    ],
                }
            ],
            "allowed_mentions": {"parse": []},
        }

    def _get_owned_webhook(self, db: Session, user: User, webhook_id: str) -> Webhook:
        webhook = db.exec(
            select(Webhook).where(Webhook.id == webhook_id, Webhook.owner_user_id == user.id)
        ).first()
        if webhook is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
        return webhook


def get_outbound_http_client(settings: Annotated[Settings, Depends(get_settings)]) -> OutboundHttpClient:
    return OutboundHttpClient(settings)


def get_webhook_service(
    settings: Annotated[Settings, Depends(get_settings)],
    outbound_http_client: Annotated[OutboundHttpClient, Depends(get_outbound_http_client)],
) -> WebhookService:
    return WebhookService(SsrfGuard(settings.ssrf_allowed_domains), outbound_http_client)
