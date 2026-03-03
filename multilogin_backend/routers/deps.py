from __future__ import annotations

from fastapi import Request

from multilogin_backend.services.mlx_client import MultiloginClient


def get_mlx_client(request: Request) -> MultiloginClient:
    return request.app.state.mlx_client
