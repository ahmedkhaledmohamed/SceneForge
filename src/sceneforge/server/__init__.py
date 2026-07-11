"""SceneForge Studio server: JSON API + static SPA serving.

create_app(home) serves:
  /api/...   — the JSON API over profiles in home (SCENEFORGE_HOME)
  /          — the built React app from sceneforge/web_dist (when present)

Site-wide auth: set SCENEFORGE_PASSWORD env var to require login.
The SPA posts to /api/site-login and stores the token.
"""

import os
import secrets
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .api import make_router

_site_tokens: set[str] = set()


class SiteAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, password: str):
        super().__init__(app)
        self.password = password

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path == "/api/site-login" or path == "/api/site-check":
            return await call_next(request)
        if path.startswith("/assets/") or path == "/favicon.ico":
            return await call_next(request)
        # SPA HTML is always served (the login screen is part of it)
        if not path.startswith("/api/"):
            return await call_next(request)
        token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
        if token and token in _site_tokens:
            return await call_next(request)
        return JSONResponse(
            {"error": {"code": "site_auth", "message": "Site login required"}},
            status_code=401,
        )


def create_app_from_env() -> FastAPI:
    from ..profile import home_dir
    home = home_dir()
    home.mkdir(parents=True, exist_ok=True)
    return create_app(home)


def create_app(home: Path) -> FastAPI:
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(
        title="SceneForge Studio API",
        description="Profile-scoped AI video production — 53 endpoints for generation, "
                    "outfits, scenes, clips, export, and settings.",
        version="1.0.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    site_password = os.environ.get("SCENEFORGE_PASSWORD")
    if site_password:
        app.add_middleware(SiteAuthMiddleware, password=site_password)

    app.include_router(make_router(home.resolve()), prefix="/api")

    @app.post("/api/site-login")
    def site_login(payload: dict):
        pw = os.environ.get("SCENEFORGE_PASSWORD")
        if not pw:
            return {"token": "no-auth", "required": False}
        if payload.get("password") != pw:
            raise HTTPException(401, detail={"code": "unauthorized", "message": "Wrong password"})
        token = secrets.token_urlsafe(32)
        _site_tokens.add(token)
        return {"token": token}

    @app.get("/api/site-check")
    def site_check():
        return {"required": bool(os.environ.get("SCENEFORGE_PASSWORD"))}

    @app.exception_handler(HTTPException)
    async def error_shape(request, exc: HTTPException):
        detail = (exc.detail if isinstance(exc.detail, dict)
                  else {"code": "error", "message": str(exc.detail)})
        return JSONResponse({"error": detail}, status_code=exc.status_code)

    web_dist = Path(__file__).resolve().parent.parent / "web_dist"

    if (web_dist / "index.html").is_file():
        from fastapi.staticfiles import StaticFiles

        app.mount("/assets", StaticFiles(directory=web_dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path == "api" or path.startswith("api/"):
                return JSONResponse(
                    {"error": {"code": "not_found", "message": "No such route"}},
                    status_code=404,
                )
            candidate = (web_dist / path).resolve()
            if path and candidate.is_file() and candidate.is_relative_to(web_dist):
                return FileResponse(candidate)
            return FileResponse(web_dist / "index.html")
    else:
        @app.get("/", include_in_schema=False)
        def placeholder():
            return JSONResponse({
                "sceneforge": "API is running at /api",
                "note": "frontend not built — run `npm run build` in frontend/",
            })

    return app
