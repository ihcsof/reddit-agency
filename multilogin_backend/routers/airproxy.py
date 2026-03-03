from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from multilogin_backend.config import Settings, get_settings


router = APIRouter(prefix="/airproxy", tags=["airproxy"])


@router.get("/proxy")
async def airproxy_proxy_config(
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    if not settings.airproxy_password:
        raise HTTPException(
            status_code=400,
            detail="AIRPROXY_PASSWORD is required for this endpoint",
        )

    return {
        "type": "http",
        "host": settings.airproxy_host,
        "port": settings.airproxy_port,
        "username": settings.airproxy_username,
        "password": settings.airproxy_password,
    }
