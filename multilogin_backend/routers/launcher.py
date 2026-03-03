from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from multilogin_backend.routers.deps import get_mlx_client
from multilogin_backend.services.mlx_client import MultiloginClient


router = APIRouter(prefix="/launcher", tags=["launcher"])


class LauncherQuickProfileRequest(BaseModel):
    model_config = ConfigDict(extra="allow")


async def _extract_body(request: Request) -> tuple[Any | None, bytes | None]:
    body = await request.body()
    if not body:
        return None, None

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        return await request.json(), None

    return None, body


@router.get("/profile/f/{folder_id}/p/{profile_id}/start")
async def start_profile(
    folder_id: str,
    profile_id: str,
    request: Request,
    client: MultiloginClient = Depends(get_mlx_client),
):
    path = f"/api/v2/profile/f/{folder_id}/p/{profile_id}/start"
    return await client.request(
        "GET",
        path,
        upstream="launcher",
        params=list(request.query_params.multi_items()),
        headers=request.headers,
    )


@router.get("/profile/status/p/{profile_id}")
async def profile_status(
    profile_id: str,
    request: Request,
    client: MultiloginClient = Depends(get_mlx_client),
):
    path = f"/profile/status/p/{profile_id}"
    return await client.request(
        "GET",
        path,
        upstream="launcher",
        params=list(request.query_params.multi_items()),
        headers=request.headers,
    )


@router.get("/profile/stop/p/{profile_id}")
async def stop_profile(
    profile_id: str,
    request: Request,
    client: MultiloginClient = Depends(get_mlx_client),
):
    path = f"/profile/stop/p/{profile_id}"
    return await client.request(
        "GET",
        path,
        upstream="launcher",
        params=list(request.query_params.multi_items()),
        headers=request.headers,
    )


@router.post("/profile/quick")
async def quick_profile(
    payload: LauncherQuickProfileRequest,
    client: MultiloginClient = Depends(get_mlx_client),
):
    return await client.request(
        "POST",
        "/api/v3/profile/quick",
        upstream="launcher",
        json=payload.model_dump(),
    )


@router.api_route(
    "/raw/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def launcher_passthrough(
    path: str,
    request: Request,
    client: MultiloginClient = Depends(get_mlx_client),
):
    json_body, raw_body = await _extract_body(request)
    return await client.request(
        request.method,
        f"/{path}",
        upstream="launcher",
        params=list(request.query_params.multi_items()),
        json=json_body,
        content=raw_body,
        headers=request.headers,
    )
