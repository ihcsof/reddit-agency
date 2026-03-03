from __future__ import annotations

from copy import deepcopy

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from multilogin_backend.config import Settings, get_settings


router = APIRouter(prefix="/airproxy", tags=["airproxy"])


class InjectProxyRequest(BaseModel):
    payload: dict
    path: str = "proxy"


def _default_proxy(settings: Settings) -> dict[str, object]:
    if not settings.airproxy_password:
        raise HTTPException(
            status_code=500,
            detail="AIRPROXY_PASSWORD is required for /airproxy/default-proxy",
        )

    return {
        "type": "http",
        "host": settings.airproxy_host,
        "port": settings.airproxy_port,
        "username": settings.airproxy_username,
        "password": settings.airproxy_password,
    }


@router.get("/default-proxy")
async def airproxy_default_proxy(
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    return _default_proxy(settings)


@router.post("/inject")
async def inject_proxy(
    payload: InjectProxyRequest,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    target = deepcopy(payload.payload)
    cursor = target
    parts = [part for part in payload.path.split(".") if part]
    for part in parts[:-1]:
        next_value = cursor.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            cursor[part] = next_value
        cursor = next_value
    leaf = parts[-1] if parts else "proxy"
    cursor[leaf] = _default_proxy(settings)
    return {"payload": target}
