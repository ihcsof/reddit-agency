from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from multilogin_backend.config import Settings, get_settings
from multilogin_backend.routers.deps import get_mlx_client
from multilogin_backend.services.mlx_client import MultiloginClient


router = APIRouter(prefix="/mlx/webhooks", tags=["webhooks"])

PROXY_DATA_URL = "https://profile-proxy.multilogin.com/v1/user"


class RefreshProxyStateRequest(BaseModel):
    profile_id: str | None = None
    extra: dict[str, Any] | None = None
    token: str | None = None


def _validate_secret(request: Request, settings: Settings) -> None:
    if not settings.mlx_webhook_secret:
        return

    received = request.headers.get("X-Webhook-Secret", "")
    if received != settings.mlx_webhook_secret:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")


@router.post("/proxy-changed")
async def proxy_changed(
    request: Request,
    payload: dict[str, Any],
    settings: Settings = Depends(get_settings),
) -> dict[str, bool]:
    _validate_secret(request, settings)

    event = {
        "received_at": datetime.now(UTC).isoformat(),
        "event": payload.get("event") or payload.get("event_type"),
        "profile_id": payload.get("profile_id") or payload.get("profileId"),
        "proxy_id": payload.get("proxy_id") or payload.get("proxyId"),
        "payload": payload,
    }
    request.app.state.proxy_events.append(event)
    return {"ok": True}


@router.get("/last-proxy-events")
async def last_proxy_events(request: Request) -> dict[str, list[dict[str, Any]]]:
    return {"events": list(request.app.state.proxy_events)}


@router.post("/refresh-proxy-state")
async def refresh_proxy_state(
    payload: RefreshProxyStateRequest,
    request: Request,
    client: MultiloginClient = Depends(get_mlx_client),
) -> Any:
    params = list((payload.extra or {}).items())
    return await client.request(
        "GET",
        PROXY_DATA_URL,
        params=params,
        headers=request.headers,
        token=payload.token,
    )
