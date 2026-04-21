"""FastAPI entrypoint for the Accessibility Remediation Copilot."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .api.meta import router as meta_router
from .api.scans import router as scans_router
from .core.config import get_settings
from .core.logging import setup_logging
from .db.base import init_db


@asynccontextmanager
async def _lifespan(app: FastAPI):
    setup_logging()
    await init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Accessibility Remediation Copilot",
        description=(
            "GenAI-powered backend for evaluating and remediating web "
            "accessibility issues on e-commerce and SMB sites."
        ),
        version="0.1.0",
        lifespan=_lifespan,
        contact={"name": "Accessibility Remediation Copilot"},
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )

    app.include_router(meta_router)
    app.include_router(scans_router)

    # Mount artifacts + static UI.
    artifacts = Path(settings.artifacts_dir).resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    app.mount("/artifacts", StaticFiles(directory=str(artifacts)), name="artifacts")

    static_dir = Path(__file__).resolve().parent.parent / "static"
    if static_dir.exists():
        app.mount("/ui", StaticFiles(directory=str(static_dir), html=True), name="ui")

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/ui/")

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> FileResponse | dict:
        fav = static_dir / "favicon.svg"
        if fav.exists():
            return FileResponse(str(fav))
        return {}

    return app


app = create_app()
