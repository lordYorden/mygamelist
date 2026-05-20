from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe


@dataclass
class BrowserSession:
    access_token: str
    expires_at: datetime


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, BrowserSession] = {}

    def create(self, access_token: str, expires_in: int) -> str:
        session_id = token_urlsafe(32)
        self._sessions[session_id] = BrowserSession(
            access_token=access_token,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        )
        return session_id

    def get(self, session_id: str | None) -> BrowserSession | None:
        if session_id is None:
            return None
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.expires_at <= datetime.now(timezone.utc):
            self.delete(session_id)
            return None
        return session

    def delete(self, session_id: str | None) -> None:
        if session_id is not None:
            self._sessions.pop(session_id, None)


session_store = SessionStore()
