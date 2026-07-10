"""SceneForge Studio server: JSON API + static SPA serving.

create_app(home) serves:
  /api/...   — the JSON API over profiles in home (SCENEFORGE_HOME)
  /          — the built React app from sceneforge/web_dist (when present)
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from .api import make_router


def create_app(home: Path) -> FastAPI:
    app = FastAPI(title="SceneForge Studio")
    app.include_router(make_router(home.resolve()), prefix="/api")

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
