from __future__ import annotations

import hashlib
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from multilogin_backend.routers.deps import get_mlx_client
from multilogin_backend.services.mlx_client import MultiloginClient


router = APIRouter(prefix="/mlx", tags=["mlx"])

PROXY_DATA_URL = "https://profile-proxy.multilogin.com/v1/user"


class ProfileLoginRequest(BaseModel):
    password: str
    profile_id: str
    password_is_md5: bool = False


def _md5_hexdigest(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()


async def _extract_body(request: Request) -> tuple[Any | None, bytes | None]:
    body = await request.body()
    if not body:
        return None, None

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        return await request.json(), None

    return None, body


@router.post("/login")
@router.post("/auth/login")
@router.post("/profile/login")
async def profile_login(
    payload: ProfileLoginRequest,
    client: MultiloginClient = Depends(get_mlx_client),
):
    upstream_payload = {
        "profile_id": payload.profile_id,
        "password": payload.password if payload.password_is_md5 else _md5_hexdigest(payload.password),
    }
    return await client.request("POST", "/profile/login", json=upstream_payload)


@router.get("/proxy/user")
@router.get("/proxy/fetch-data")
async def fetch_proxy_data(
    request: Request,
    client: MultiloginClient = Depends(get_mlx_client),
):
    return await client.request(
        "GET",
        PROXY_DATA_URL,
        params=list(request.query_params.multi_items()),
        headers=request.headers,
    )

@router.post("/profile/search")
async def profile_search(
    request: Request,
    client: MultiloginClient = Depends(get_mlx_client),
):
    json_body, raw_body = await _extract_body(request)
    return await client.request(
        "POST",
        "/profile/search",
        json=json_body,
        content=raw_body,
        headers=request.headers,
    )


@router.post("/profile/metas")
async def profile_metas(
    request: Request,
    client: MultiloginClient = Depends(get_mlx_client),
):
    json_body, raw_body = await _extract_body(request)
    return await client.request(
        "POST",
        "/profile/metas",
        json=json_body,
        content=raw_body,
        headers=request.headers,
    )


@router.api_route(
    "/raw/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def mlx_passthrough(
    path: str,
    request: Request,
    client: MultiloginClient = Depends(get_mlx_client),
):
    json_body, raw_body = await _extract_body(request)
    return await client.request(
        request.method,
        f"/{path}",
        upstream="mlx",
        params=list(request.query_params.multi_items()),
        json=json_body,
        content=raw_body,
        headers=request.headers,
    )
