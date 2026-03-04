from __future__ import annotations

from collections.abc import Mapping

import httpx
from fastapi import HTTPException
from fastapi.responses import JSONResponse, Response

from multilogin_backend.config import Settings
from multilogin_backend.services.upstream_http import (
    UpstreamHttpClient,
    UpstreamName,
    UpstreamRequestError,
)


class MultiloginClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = UpstreamHttpClient(settings)

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
        resolved_token = self._resolve_token(token=token, headers=headers)

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

        if response.is_success:
            return self._build_response(response)

        raise HTTPException(
            status_code=response.status_code,
            detail=self._extract_error_detail(response),
        )

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
