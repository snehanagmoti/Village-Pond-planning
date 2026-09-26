"""Single-origin frontend and API entry point for the allotted dev machines.

Run ``uvicorn web:create_app --factory`` from backend/ after building frontend/.
The existing ``main:app`` entry point remains available for API-only hosting.
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import FileResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from main import app as api_app
from main import settings


class FrontendAssets(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response


def create_app(frontend_dir: str | Path | None = None) -> Starlette:
    directory = Path(frontend_dir or os.environ.get(
        "FRONTEND_DIST", str(Path(__file__).resolve().parents[1] / "frontend" / "dist")
    )).resolve()
    if not (directory / "index.html").is_file() or not (directory / "assets").is_dir():
        raise RuntimeError(f"Frontend build missing at {directory}; run npm run build first")

    async def index(request):
        return FileResponse(directory / "index.html", headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "strict-origin-when-cross-origin",
        })

    async def favicon(request):
        return FileResponse(directory / "favicon.svg", headers={
            "Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff",
        })

    @asynccontextmanager
    async def lifespan(application):
        async with api_app.router.lifespan_context(api_app):
            yield

    return Starlette(
        lifespan=lifespan,
        middleware=[Middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)],
        routes=[
            Route("/", index),
            Route("/favicon.svg", favicon),
            Mount("/assets", app=FrontendAssets(directory=directory / "assets")),
            Mount("/", app=api_app),
        ],
    )
