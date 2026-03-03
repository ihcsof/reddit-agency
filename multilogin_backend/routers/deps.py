from __future__ import annotations

from fastapi import Request

from multilogin_backend.playwright_runtime import DemoAutomationRuntime
from multilogin_backend.services.mlx_client import MultiloginClient


def get_mlx_client(request: Request) -> MultiloginClient:
    return request.app.state.mlx_client


def get_demo_runtime(request: Request) -> DemoAutomationRuntime:
    return request.app.state.demo_runtime
