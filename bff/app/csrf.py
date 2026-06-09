from secrets import compare_digest, token_urlsafe
from urllib.parse import parse_qs

from fastapi import Request, status
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from .config import get_settings

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
FORM_URLENCODED = "application/x-www-form-urlencoded"


class CsrfMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        settings = get_settings()
        expected_token = request.cookies.get(settings.csrf_cookie_name)

        if request.method.upper() in UNSAFE_METHODS:
            actual_token = request.headers.get(settings.csrf_header_name)
            if actual_token is None:
                actual_token = await self._form_token(request, settings.csrf_form_field)

            if (
                expected_token is None
                or actual_token is None
                or not compare_digest(expected_token, actual_token)
            ):
                response = self._reject()
                self._ensure_cookie(response, settings.csrf_cookie_name, expected_token, settings.cookie_secure)
                return response

        response = await call_next(request)
        self._ensure_cookie(response, settings.csrf_cookie_name, expected_token, settings.cookie_secure)
        return response

    async def _form_token(self, request: Request, field_name: str) -> str | None:
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != FORM_URLENCODED:
            return None

        body = await request.body()

        async def receive() -> dict[str, object]:
            return {"type": "http.request", "body": body, "more_body": False}

        request._receive = receive
        form = parse_qs(body.decode(), keep_blank_values=True)
        values = form.get(field_name)
        return values[0] if values else None

    def _ensure_cookie(self, response: Response, cookie_name: str, token: str | None, secure: bool) -> None:
        response.set_cookie(
            key=cookie_name,
            value=token or token_urlsafe(32),
            httponly=False,
            secure=secure,
            samesite="strict",
            path="/",
        )

    def _reject(self) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "CSRF token missing or invalid"},
        )
