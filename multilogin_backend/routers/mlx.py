from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from multilogin_backend.routers.deps import get_mlx_client
from multilogin_backend.services.mlx_client import MultiloginClient


router = APIRouter(prefix="/mlx", tags=["mlx"])


class SignInRequest(BaseModel):
    email: str
    password: str
    password_is_md5: bool = False


class RefreshTokenRequest(BaseModel):
    email: str
    refresh_token: str
    workspace_id: str


async def _extract_body(request: Request) -> tuple[Any | None, bytes | None]:
    body = await request.body()
    if not body:
        return None, None

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        return await request.json(), None

    return None, body


@router.post("/user/signin")
async def user_signin(
    payload: SignInRequest,
    client: MultiloginClient = Depends(get_mlx_client),
):
    upstream_payload = {
        "email": payload.email,
        "password": payload.password,
    }
    return await client.request("POST", "/user/signin", json=upstream_payload)


@router.post("/user/refresh-token")
async def refresh_token(
    payload: RefreshTokenRequest,
    client: MultiloginClient = Depends(get_mlx_client),
):
    return await client.request("POST", "/user/refresh_token", json=payload.model_dump())


@router.get("/user/workspaces")
async def user_workspaces(
    request: Request,
    client: MultiloginClient = Depends(get_mlx_client),
):
    return await client.request(
        "GET",
        "/user/workspaces",
        params=list(request.query_params.multi_items()),
        headers=request.headers,
    )


@router.get("/workspace/automation-token")
async def workspace_automation_token(
    request: Request,
    client: MultiloginClient = Depends(get_mlx_client),
):
    return await client.request(
        "GET",
        "/workspace/automation_token",
        params=list(request.query_params.multi_items()),
        headers=request.headers,
    )


@router.api_route(
    "/{path:path}",
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
