from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Literal

import httpx
from fastapi import HTTPException
from fastapi.responses import JSONResponse, Response

from multilogin_backend.config import Settings
from multilogin_backend.services.upstream_http import (
    UpstreamHttpClient,
    UpstreamName,
    UpstreamRequestError,
)


TokenSource = Literal["header", "param", "settings", "none"]


class MultiloginClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = UpstreamHttpClient(settings)
        self.token = settings.mlx_token
        self._refresh_lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def request(
        self,
        method: str,
        url_or_path: str,
        *,
        upstream: UpstreamName = "mlx",
        token: str | None = None,
        params: list[tuple[str, str]] | None = None,
        json: object | None = None,
        content: bytes | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Response:
        request_headers = self._sanitize_headers(headers)
        request_headers.setdefault("Accept-Encoding", "identity")
        resolved_token, token_source = self._resolve_token(token=token, headers=headers)

        try:
            response = await self._client.request(
                method=method.upper(),
                url_or_path=url_or_path,
                upstream=upstream,
                token=resolved_token,
                params=params,
                json=json,
                content=content,
                headers=request_headers,
            )
        except UpstreamRequestError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

        if (
            upstream == "mlx"
            and token_source == "settings"
            and response.status_code == 401
        ):
            await self.refresh_token()
            try:
                response = await self._client.request(
                    method=method.upper(),
                    url_or_path=url_or_path,
                    upstream=upstream,
                    token=self.token,
                    params=params,
                    json=json,
                    content=content,
                    headers=request_headers,
                )
            except UpstreamRequestError as exc:
                raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

            if response.status_code == 401:
                raise HTTPException(
                    status_code=401,
                    detail="Multilogin token invalid/expired even after refresh",
                )

        if response.is_success:
            return self._build_response(response)

        raise HTTPException(
            status_code=response.status_code,
            detail=self._extract_error_detail(response),
        )

    async def refresh_token(self) -> str:
        async with self._refresh_lock:
            if not self._settings.mlx_refresh_token:
                raise HTTPException(status_code=500, detail="MLX_REFRESH_TOKEN is required")
            if not self._settings.mlx_email:
                raise HTTPException(status_code=500, detail="MLX_EMAIL is required")
            if not self._settings.mlx_workspace_id:
                raise HTTPException(status_code=500, detail="MLX_WORKSPACE_ID is required")
            if not self.token:
                raise HTTPException(status_code=500, detail="MLX_TOKEN is required")

            payload = {
                "email": self._settings.mlx_email,
                "refresh_token": self._settings.mlx_refresh_token,
                "workspace_id": self._settings.mlx_workspace_id,
            }

            try:
                response = await self._client._client.post(
                    f"{self._settings.mlx_base_url}/user/refresh_token",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Content-Type": "application/json",
                    },
                )
            except httpx.HTTPError as exc:
                raise HTTPException(
                    status_code=502,
                    detail="Failed refreshing MLX token: failed to reach upstream service",
                ) from exc

            if response.status_code != 200:
                detail = self._safe_text(response).strip() or f"upstream status {response.status_code}"
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed refreshing MLX token: {detail}",
                )

            try:
                data = response.json()
            except ValueError as exc:
                raise HTTPException(
                    status_code=502,
                    detail="Token refresh response was not valid JSON",
                ) from exc

            new_token = data.get("data", {}).get("token") if isinstance(data, Mapping) else None
            if not new_token:
                raise HTTPException(status_code=502, detail="Token refresh response missing token")

            self.token = str(new_token)
            return self.token

    def _resolve_token(
        self,
        *,
        token: str | None,
        headers: Mapping[str, str] | None,
    ) -> tuple[str | None, TokenSource]:
        header_token = None
        if headers is not None:
            for key, value in headers.items():
                if key.lower() == "x-mlx-token" and value:
                    header_token = value
                    break

        if header_token:
            return header_token, "header"
        if token:
            return token, "param"
        if self.token:
            return self.token, "settings"
        return None, "none"

    def _sanitize_headers(self, headers: Mapping[str, str] | None) -> dict[str, str]:
        if headers is None:
            return {}

        ignored = {"accept-encoding", "authorization", "content-length", "host", "x-mlx-token"}
        return {
            key: value
            for key, value in headers.items()
            if key.lower() not in ignored
        }

    def _build_response(self, response: httpx.Response) -> Response:
        if response.status_code == 204 or not response.content:
            return Response(status_code=response.status_code)

        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            payload = self._try_parse_json(response)
            if payload is not None:
                return JSONResponse(content=payload, status_code=response.status_code)

        return Response(
            content=response.content,
            status_code=response.status_code,
            media_type=content_type or None,
        )

    def _extract_error_detail(self, response: httpx.Response) -> object:
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            payload = self._try_parse_json(response)
            if payload is not None:
                return payload

        text = self._safe_text(response).strip()
        return text or "Upstream request failed"

    def _try_parse_json(self, response: httpx.Response) -> object | None:
        try:
            return response.json()
        except (ValueError, UnicodeDecodeError):
            return None

    def _safe_text(self, response: httpx.Response) -> str:
        try:
            return response.text
        except UnicodeDecodeError:
            return response.content.decode("utf-8", errors="replace")
