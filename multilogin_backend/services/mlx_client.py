from __future__ import annotations

from collections.abc import Mapping
from typing import Literal
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException
from fastapi.responses import JSONResponse, Response

from multilogin_backend.config import Settings


UpstreamName = Literal["mlx", "launcher"]


class MultiloginClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            timeout=settings.mlx_timeout_s,
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        upstream: UpstreamName = "mlx",
        token: str | None = None,
        params: list[tuple[str, str]] | None = None,
        json: object | None = None,
        content: bytes | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Response:
        request_headers = self._sanitize_headers(headers)
        resolved_token = self._resolve_token(token=token, headers=headers)
        if resolved_token:
            request_headers["Authorization"] = f"Bearer {resolved_token}"

        url = self._build_url(path=path, upstream=upstream)

        try:
            response = await self._client.request(
                method=method.upper(),
                url=url,
                params=params,
                json=json,
                content=content,
                headers=request_headers,
            )
        except httpx.TimeoutException as exc:
            raise HTTPException(status_code=504, detail="Upstream request timed out") from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="Failed to reach upstream service") from exc

        if response.is_success:
            return self._build_response(response)

        raise HTTPException(
            status_code=response.status_code,
            detail=self._extract_error_detail(response),
        )

    def _build_url(self, *, path: str, upstream: UpstreamName) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path

        base_url = (
            self._settings.mlx_base_url
            if upstream == "mlx"
            else self._settings.mlx_launcher_base_url
        )
        normalized_path = path if path.startswith("/") else f"/{path}"

        if upstream == "launcher" and normalized_path.startswith("/api/"):
            parts = urlsplit(base_url)
            return f"{parts.scheme}://{parts.netloc}{normalized_path}"

        return f"{base_url}{normalized_path}"

    def _resolve_token(
        self,
        *,
        token: str | None,
        headers: Mapping[str, str] | None,
    ) -> str | None:
        header_token = None
        if headers is not None:
            for key, value in headers.items():
                if key.lower() == "x-mlx-token" and value:
                    header_token = value
                    break

        if header_token:
            return header_token
        if token:
            return token
        if self._settings.mlx_token:
            return self._settings.mlx_token
        return None

    def _sanitize_headers(self, headers: Mapping[str, str] | None) -> dict[str, str]:
        if headers is None:
            return {}

        ignored = {"authorization", "content-length", "host", "x-mlx-token"}
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
            return JSONResponse(content=response.json(), status_code=response.status_code)

        return Response(
            content=response.content,
            status_code=response.status_code,
            media_type=content_type or None,
        )

    def _extract_error_detail(self, response: httpx.Response) -> object:
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                return response.json()
            except ValueError:
                pass

        text = response.text.strip()
        return text or "Upstream request failed"
