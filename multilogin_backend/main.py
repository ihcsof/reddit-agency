from __future__ import annotations

from collections import deque
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from multilogin_backend.config import get_settings
from multilogin_backend.routers.airproxy import router as airproxy_router
from multilogin_backend.routers.frontend import router as frontend_router
from multilogin_backend.routers.health import router as health_router
from multilogin_backend.routers.launcher import router as launcher_router
from multilogin_backend.routers.mlx import router as mlx_router
from multilogin_backend.routers.webhooks import router as webhook_router
from multilogin_backend.services.mlx_client import MultiloginClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    app.state.mlx_client = MultiloginClient(settings)
    app.state.proxy_events = deque(maxlen=100)
    try:
        yield
    finally:
        await app.state.mlx_client.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Multilogin API Proxy", lifespan=lifespan)
    if settings.app_cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.app_cors_origins),
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.include_router(frontend_router)
    app.include_router(health_router)
    app.include_router(mlx_router)
    app.include_router(webhook_router)
    app.include_router(launcher_router)
    app.include_router(airproxy_router)
    return app


app = create_app()
