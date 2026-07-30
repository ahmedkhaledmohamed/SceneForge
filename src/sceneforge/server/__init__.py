"""SceneForge Studio server: JSON API + static SPA + multi-user auth.

create_app(home) serves:
  /api/auth/...  — signup, login, logout, OAuth flows
  /api/...       — the profile-scoped JSON API (requires auth)
  /landing/...   — static marketing site (public)
  /              — redirects to /landing/
  /*             — the built React SPA (requires auth via frontend)
"""

import os
from pathlib import Path
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .api import make_router
from .auth import AuthDB


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, auth_db: AuthDB):
        super().__init__(app)
        self.auth_db = auth_db

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path == "/" or path.startswith("/landing"):
            return await call_next(request)
        if path.startswith("/api/auth/"):
            return await call_next(request)
        if path == "/api/site-check":
            return await call_next(request)
        if path.startswith("/assets/") or path == "/favicon.ico":
            return await call_next(request)
        if "/media/" in path:
            return await call_next(request)
        if not path.startswith("/api/"):
            return await call_next(request)

        token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
        user = self.auth_db.validate_session(token) if token else None
        if not user:
            return JSONResponse(
                {"error": {"code": "unauthorized", "message": "Login required"}},
                status_code=401,
            )
        request.state.user = user
        return await call_next(request)


def create_app_from_env() -> FastAPI:
    from ..profile import home_dir
    home = home_dir()
    home.mkdir(parents=True, exist_ok=True)
    return create_app(home)


def create_app(home: Path) -> FastAPI:
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(
        title="SceneForge Studio API",
        description="Profile-scoped AI video production with multi-user auth.",
        version="2.0.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    db_path = home.resolve() / "sceneforge_auth.db"
    auth_db = AuthDB(db_path)
    app.state.auth_db = auth_db

    app.add_middleware(AuthMiddleware, auth_db=auth_db)

    app.include_router(make_router(home.resolve()), prefix="/api")

    # -------------------------------------------------------- auth routes

    base_url = os.environ.get("SCENEFORGE_BASE_URL", "").rstrip("/")
    google_client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    google_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    github_client_id = os.environ.get("GITHUB_CLIENT_ID", "")
    github_client_secret = os.environ.get("GITHUB_CLIENT_SECRET", "")

    @app.post("/api/auth/signup")
    def auth_signup(payload: dict):
        email = (payload.get("email") or "").strip().lower()
        password = payload.get("password") or ""
        name = (payload.get("name") or "").strip()
        if not email or "@" not in email:
            raise HTTPException(400, detail={"code": "invalid", "message": "Valid email required"})
        if len(password) < 8:
            raise HTTPException(400, detail={"code": "invalid", "message": "Password must be at least 8 characters"})
        if auth_db.get_user_by_email(email):
            raise HTTPException(409, detail={"code": "exists", "message": "Account already exists"})
        user = auth_db.create_user(email=email, name=name or email.split("@")[0], password=password)
        token = auth_db.create_session(user["id"])
        return {"token": token, "user": _user_doc(user)}

    @app.post("/api/auth/login")
    def auth_login(payload: dict):
        from .auth import _check_password
        email = (payload.get("email") or "").strip().lower()
        password = payload.get("password") or ""
        user = auth_db.get_user_by_email(email)
        if not user or not user["password_hash"]:
            raise HTTPException(401, detail={"code": "unauthorized", "message": "Invalid email or password"})
        if not _check_password(password, user["password_hash"]):
            raise HTTPException(401, detail={"code": "unauthorized", "message": "Invalid email or password"})
        token = auth_db.create_session(user["id"])
        return {"token": token, "user": _user_doc(user)}

    @app.post("/api/auth/logout")
    def auth_logout(request: Request):
        token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
        if token:
            auth_db.revoke_session(token)
        return {"ok": True}

    @app.get("/api/auth/me")
    def auth_me(request: Request):
        token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
        user = auth_db.validate_session(token) if token else None
        if not user:
            return {"user": None, "preferences": {}}
        prefs = auth_db.get_preferences(user["id"])
        return {"user": _user_doc(user), "preferences": prefs}

    @app.get("/api/auth/preferences")
    def get_preferences(request: Request):
        token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
        user = auth_db.validate_session(token) if token else None
        if not user:
            raise HTTPException(401, detail={"code": "unauthorized", "message": "Login required"})
        return auth_db.get_preferences(user["id"])

    @app.patch("/api/auth/preferences")
    def patch_preferences(request: Request, payload: dict):
        token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
        user = auth_db.validate_session(token) if token else None
        if not user:
            raise HTTPException(401, detail={"code": "unauthorized", "message": "Login required"})
        allowed = {"last_profile", "theme", "onboarding_completed"}
        filtered = {k: v for k, v in payload.items() if k in allowed}
        return auth_db.set_preferences(user["id"], filtered)

    @app.get("/api/auth/providers")
    def auth_providers():
        return {
            "google": bool(google_client_id),
            "github": bool(github_client_id),
            "email": True,
        }

    # --- Google OAuth ---
    @app.get("/api/auth/google")
    def auth_google_start():
        if not google_client_id:
            raise HTTPException(400, detail={"code": "disabled", "message": "Google sign-in not configured"})
        state = auth_db.save_oauth_state("google")
        params = urlencode({
            "client_id": google_client_id,
            "redirect_uri": f"{base_url}/api/auth/google/callback",
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "offline",
            "prompt": "select_account",
        })
        return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")

    @app.get("/api/auth/google/callback")
    async def auth_google_callback(code: str = "", state: str = ""):
        if not auth_db.consume_oauth_state(state):
            raise HTTPException(400, detail={"code": "invalid", "message": "Invalid or expired OAuth state"})
        async with httpx.AsyncClient() as client:
            token_resp = await client.post("https://oauth2.googleapis.com/token", data={
                "code": code,
                "client_id": google_client_id,
                "client_secret": google_client_secret,
                "redirect_uri": f"{base_url}/api/auth/google/callback",
                "grant_type": "authorization_code",
            })
            if token_resp.status_code != 200:
                raise HTTPException(400, detail={"code": "oauth_failed", "message": "Google token exchange failed"})
            tokens = token_resp.json()
            userinfo_resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
            info = userinfo_resp.json()
        user = auth_db.get_or_create_oauth_user(
            email=info["email"], name=info.get("name", ""),
            avatar_url=info.get("picture", ""),
            provider="google", provider_id=info["id"],
        )
        session_token = auth_db.create_session(user["id"])
        return RedirectResponse(f"/app?token={session_token}")

    # --- GitHub OAuth ---
    @app.get("/api/auth/github")
    def auth_github_start():
        if not github_client_id:
            raise HTTPException(400, detail={"code": "disabled", "message": "GitHub sign-in not configured"})
        state = auth_db.save_oauth_state("github")
        params = urlencode({
            "client_id": github_client_id,
            "redirect_uri": f"{base_url}/api/auth/github/callback",
            "scope": "user:email",
            "state": state,
        })
        return RedirectResponse(f"https://github.com/login/oauth/authorize?{params}")

    @app.get("/api/auth/github/callback")
    async def auth_github_callback(code: str = "", state: str = ""):
        if not auth_db.consume_oauth_state(state):
            raise HTTPException(400, detail={"code": "invalid", "message": "Invalid or expired OAuth state"})
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                "https://github.com/login/oauth/access_token",
                json={"client_id": github_client_id, "client_secret": github_client_secret, "code": code},
                headers={"Accept": "application/json"},
            )
            if token_resp.status_code != 200:
                raise HTTPException(400, detail={"code": "oauth_failed", "message": "GitHub token exchange failed"})
            access_token = token_resp.json().get("access_token")
            user_resp = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            gh_user = user_resp.json()
            email = gh_user.get("email")
            if not email:
                emails_resp = await client.get(
                    "https://api.github.com/user/emails",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                for e in emails_resp.json():
                    if e.get("primary"):
                        email = e["email"]
                        break
            if not email:
                raise HTTPException(400, detail={"code": "no_email", "message": "Could not get email from GitHub"})
        user = auth_db.get_or_create_oauth_user(
            email=email, name=gh_user.get("name") or gh_user.get("login", ""),
            avatar_url=gh_user.get("avatar_url", ""),
            provider="github", provider_id=str(gh_user["id"]),
        )
        session_token = auth_db.create_session(user["id"])
        return RedirectResponse(f"/app?token={session_token}")

    # --- backwards compat ---
    @app.get("/api/site-check")
    def site_check():
        return {"required": True, "auth": "multi-user"}

    @app.exception_handler(HTTPException)
    async def error_shape(request, exc: HTTPException):
        detail = (exc.detail if isinstance(exc.detail, dict)
                  else {"code": "error", "message": str(exc.detail)})
        return JSONResponse({"error": detail}, status_code=exc.status_code)

    # ------------------------------------------------- static file serving

    web_dist = Path(__file__).resolve().parent.parent / "web_dist"

    _landing_env = os.environ.get("SCENEFORGE_LANDING_DIR")
    if _landing_env:
        site_dir = Path(_landing_env)
    else:
        site_dir = Path(__file__).resolve().parent.parent.parent.parent / "site"

    has_landing = site_dir.is_dir() and (site_dir / "index.html").is_file()

    @app.get("/", include_in_schema=False)
    def root_redirect():
        if has_landing:
            return RedirectResponse("/landing/", status_code=302)
        return JSONResponse({"sceneforge": "API running at /api"})

    if has_landing:
        @app.get("/landing", include_in_schema=False)
        def landing_root():
            return FileResponse(site_dir / "index.html")

        @app.get("/landing/{path:path}", include_in_schema=False)
        def landing_files(path: str):
            candidate = (site_dir / path).resolve()
            if candidate.is_file() and candidate.is_relative_to(site_dir):
                return FileResponse(candidate)
            if not path or path.endswith("/"):
                return FileResponse(site_dir / "index.html")
            html = site_dir / (path + ".html")
            if html.is_file():
                return FileResponse(html)
            return FileResponse(site_dir / "index.html")

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

    return app


def _user_doc(user: dict) -> dict:
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "avatar_url": user["avatar_url"],
        "provider": user["provider"],
    }
