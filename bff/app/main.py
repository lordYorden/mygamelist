from pathlib import Path
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, Form, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings, get_settings
from .sessions import session_store

app = FastAPI(title="MyGameList BFF")
frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/login")
async def login(
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    username: str = Form(...),
    password: str = Form(...),
) -> dict[str, str | bool]:
    async with httpx.AsyncClient(base_url=settings.api_base_url) as client:
        api_response = await client.post(
            "/api/auth/token",
            json={"username": username, "password": password},
        )

    if api_response.status_code == status.HTTP_401_UNAUTHORIZED:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if api_response.status_code >= 400:
        raise HTTPException(status_code=api_response.status_code, detail="Login failed")

    token_data = api_response.json()
    session_id = session_store.create(token_data["accessToken"], token_data["expiresIn"])
    response.set_cookie(
        key=settings.cookie_name,
        value=session_id,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        max_age=token_data["expiresIn"],
        path="/",
    )
    return {"success": True, "message": "Logged in"}


@app.post("/logout")
async def logout(
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str | bool]:
    session_store.delete(request.cookies.get(settings.cookie_name))
    response.delete_cookie(key=settings.cookie_name, path="/")
    return {"success": True, "message": "Logged out"}


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_api(
    path: str,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    body = await request.body()
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in {"host", "content-length", "authorization", "cookie"}
    }

    if path != "register":
        session = session_store.get(request.cookies.get(settings.cookie_name))
        if session is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        headers["Authorization"] = f"Bearer {session.access_token}"

    async with httpx.AsyncClient(base_url=settings.api_base_url) as client:
        api_response = await client.request(
            request.method,
            f"/api/{path}",
            content=body,
            headers=headers,
            params=request.query_params,
        )

    excluded_headers = {"content-encoding", "transfer-encoding", "connection"}
    response_headers = {
        key: value for key, value in api_response.headers.items() if key.lower() not in excluded_headers
    }
    return Response(
        content=api_response.content,
        status_code=api_response.status_code,
        headers=response_headers,
        media_type=api_response.headers.get("content-type"),
    )


if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")


@app.get("/{full_path:path}")
def serve_react_app(full_path: str) -> Response:
    index_file = frontend_dist / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Frontend has not been built. Run `npm run build` in frontend/."},
    )
