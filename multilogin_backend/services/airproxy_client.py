from __future__ import annotations

"""Async AirProxy IP rotation client.

Docs reference: https://airproxy.io/api/proxy/
"""

import asyncio
from datetime import datetime, timezone
import logging
from collections.abc import Mapping
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from multilogin_backend.config import get_settings


DEFAULT_TIMEOUT_S = 30.0
DEFAULT_RETRY_AFTER_S = 5.0

logger = logging.getLogger(__name__)


def redact_url(url: str) -> str:
    parts = urlsplit(url)
    query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() == "key":
            query.append((key, "***REDACTED***"))
            continue
        query.append((key, value))

    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


class AirProxyClient:
    def __init__(
        self,
        *,
        change_ip_url: str | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        resolved_change_ip_url = (
            change_ip_url if change_ip_url is not None else get_settings().airproxy_change_ip_url
        ).strip()
        if not resolved_change_ip_url:
            raise ValueError("AIRPROXY_CHANGE_IP_URL is required")

        self._change_ip_url = resolved_change_ip_url
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout_s)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> AirProxyClient:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.aclose()

    async def rotate_ip_and_verify(
        self,
        *,
        min_debounce_s: float = 5.0,
        max_retries: int = 1,
    ) -> dict[str, Any]:
        attempt = 0
        debounce_s = max(0.0, min_debounce_s)

        while True:
            payload = await self.change_ip(max_retries=max_retries)
            await asyncio.sleep(debounce_s)

            result = dict(payload)
            result["attempts"] = attempt + 1

            verification = self._verify_payload(payload)
            result["verification"] = verification

            if verification == "unknown":
                result.setdefault("status", "ok")
                return result

            changed = verification == "changed"
            result["changed"] = changed
            if changed:
                result.setdefault("status", "ok")
                return result

            if attempt >= max_retries:
                result["status"] = "skipped"
                result["reason"] = "ip_not_changed"
                return result

            attempt += 1
            logger.info(
                "AirProxy IP did not change, retrying rotation via %s",
                redact_url(self._change_ip_url),
            )

    async def change_ip(self, *, max_retries: int = 1) -> dict[str, Any]:
        response = await self._request_change_ip(max_retries=max_retries)
        response.raise_for_status()

        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("AirProxy response must be a JSON object")
        return payload

    async def _request_change_ip(self, *, max_retries: int = 1) -> httpx.Response:
        attempt = 0

        while True:
            response = await self._client.get(self._change_ip_url)
            if response.status_code != 429 or attempt >= max_retries:
                return response

            retry_after_s = self._get_retry_after_seconds(response.headers)
            logger.warning(
                "AirProxy rate-limited change_ip on %s; retrying in %.2fs",
                redact_url(self._change_ip_url),
                retry_after_s,
            )
            await asyncio.sleep(retry_after_s)
            attempt += 1

    def _get_retry_after_seconds(self, headers: Mapping[str, str]) -> float:
        raw_value = headers.get("Retry-After")
        if not raw_value:
            return DEFAULT_RETRY_AFTER_S

        try:
            return max(0.0, float(raw_value))
        except ValueError:
            pass

        try:
            retry_at = parsedate_to_datetime(raw_value)
        except (TypeError, ValueError, IndexError, OverflowError):
            return DEFAULT_RETRY_AFTER_S

        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)

        seconds = (retry_at - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, seconds)

    def _verify_payload(self, payload: Mapping[str, Any]) -> str:
        old_ip = payload.get("old_ip")
        new_ip = payload.get("new_ip")
        if old_ip is None or new_ip is None:
            return "unknown"
        return "changed" if old_ip != new_ip else "unchanged"


async def _main() -> None:
    logging.basicConfig(level=logging.INFO)
    async with AirProxyClient() as client:
        result = await client.rotate_ip_and_verify()
        print(result)


if __name__ == "__main__":
    asyncio.run(_main())
