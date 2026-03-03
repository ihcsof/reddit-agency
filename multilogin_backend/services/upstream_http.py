from __future__ import annotations

from collections.abc import Mapping
from typing import Literal
from urllib.parse import urlsplit

import httpx

from multilogin_backend.config import Settings


UpstreamName = Literal["mlx", "launcher"]


class UpstreamRequestError(RuntimeError):
    def __init__(self, detail: str, *, status_code: int) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class UpstreamHttpClient:
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
        url_or_path: str,
        *,
        upstream: UpstreamName = "mlx",
        token: str | None = None,
        params: list[tuple[str, str]] | None = None,
        json: object | None = None,
        content: bytes | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        request_headers = dict(headers or {})
        resolved_token = token or self._settings.mlx_token
        if resolved_token:
            request_headers["Authorization"] = f"Bearer {resolved_token}"

        url = self.build_url(url_or_path=url_or_path, upstream=upstream)

        try:
            return await self._client.request(
                method=method.upper(),
                url=url,
                params=params,
                json=json,
                content=content,
                headers=request_headers,
            )
        except httpx.TimeoutException as exc:
            raise UpstreamRequestError(
                "Upstream request timed out",
                status_code=504,
            ) from exc
        except httpx.HTTPError as exc:
            raise UpstreamRequestError(
                "Failed to reach upstream service",
                status_code=502,
            ) from exc

    def build_url(self, *, url_or_path: str, upstream: UpstreamName) -> str:
        if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
            return url_or_path

        base_url = (
            self._settings.mlx_base_url
            if upstream == "mlx"
            else self._settings.mlx_launcher_base_url
        )
        normalized_path = url_or_path if url_or_path.startswith("/") else f"/{url_or_path}"

        if upstream == "launcher" and normalized_path.startswith("/api/"):
            parts = urlsplit(base_url)
            return f"{parts.scheme}://{parts.netloc}{normalized_path}"

        return f"{base_url}{normalized_path}"
