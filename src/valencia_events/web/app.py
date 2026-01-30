"""FastAPI application for user management."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .routes import router
from .auth import auth_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events (startup/shutdown)."""
    # Startup: Ensure DB connection or other ini
    yield
    # Shutdown


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(title="Valencia Events", lifespan=lifespan)

    secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
    app.add_middleware(SessionMiddleware, secret_key=secret_key)

    static_dir = os.path.join(os.path.dirname(__file__), "static")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    app.include_router(router)
    app.include_router(auth_router)

    return app


app = create_app()
