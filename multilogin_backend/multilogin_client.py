from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
import logging
from typing import Any
from urllib.parse import urlencode

import httpx
from playwright.async_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Page,
    Playwright,
    async_playwright,
)

from multilogin_backend.config import Settings, get_settings
from multilogin_backend.services.upstream_http import UpstreamHttpClient, UpstreamRequestError


logger = logging.getLogger(__name__)
CORE_DOWNLOAD_RETRY_DELAY_S = 5.0
CORE_DOWNLOAD_MAX_RETRIES = 24


@dataclass(slots=True)
class ManagedProfileSession:
    client: "MultiloginClient"
    profile_id: str
    browser: Browser
    context: BrowserContext
    page: Page | None = None
    _closed: bool = field(default=False, init=False, repr=False)

    async def aclose(self, *, stop_profile: bool = True) -> None:
        if self._closed:
            return

        self._closed = True
        self.client._forget_session(self)
        first_error: Exception | None = None

        if self.page is not None and not self.page.is_closed():
            try:
                await self.page.close()
            except PlaywrightError as exc:
                first_error = first_error or exc

        try:
            await self.context.close()
        except PlaywrightError as exc:
            first_error = first_error or exc

        try:
            await self.browser.close()
        except PlaywrightError as exc:
            first_error = first_error or exc

        if stop_profile:
            try:
                await self.client.stop_profile(self.profile_id)
            except Exception as exc:
                first_error = first_error or exc

        if first_error is not None:
            raise first_error


class MultiloginClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._http = UpstreamHttpClient(self._settings)
        self.token = self._settings.mlx_token
        self._playwright: Playwright | None = None
        self._sessions_by_page: dict[int, ManagedProfileSession] = {}
        self._sessions_by_context: dict[int, ManagedProfileSession] = {}
        self._refresh_lock = asyncio.Lock()

    async def aclose(self) -> None:
        sessions = list(
            {
                id(session): session
                for session in (
                    list(self._sessions_by_page.values()) + list(self._sessions_by_context.values())
                )
            }.values()
        )
        for session in sessions:
            try:
                await session.aclose()
            except Exception:
                continue

        await self._http.aclose()

        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    async def request(
        self,
        method: str,
        url_or_path: str,
        *,
        upstream: str = "mlx",
        token: str | None = None,
        params: list[tuple[str, str]] | None = None,
        json: object | None = None,
        content: bytes | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        response = await self._send_request(
            method,
            url_or_path,
            upstream=upstream,
            token=token,
            params=params,
            json=json,
            content=content,
            headers=headers,
        )
        response.raise_for_status()

        if not response.content:
            return None

        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return response.json()

        return response.text

    async def refresh_token(self) -> str:
        async with self._refresh_lock:
            if not self._settings.mlx_refresh_token:
                raise RuntimeError("MLX_REFRESH_TOKEN is required to refresh the Multilogin token")
            if not self._settings.mlx_email:
                raise RuntimeError("MLX_EMAIL is required to refresh the Multilogin token")
            if not self._settings.mlx_workspace_id:
                raise RuntimeError("MLX_WORKSPACE_ID is required to refresh the Multilogin token")
            if not self.token:
                raise RuntimeError("MLX_TOKEN is required to refresh the Multilogin token")

            payload = {
                "email": self._settings.mlx_email,
                "refresh_token": self._settings.mlx_refresh_token,
                "workspace_id": self._settings.mlx_workspace_id,
            }
            headers = {"Content-Type": "application/json"}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"

            try:
                response = await self._http._client.post(
                    f"{self._settings.mlx_base_url}/user/refresh_token",
                    json=payload,
                    headers=headers,
                )
            except httpx.HTTPError as exc:
                raise RuntimeError("Failed refreshing MLX token: failed to reach upstream service") from exc

            if response.status_code != 200:
                detail = response.text.strip() or f"upstream status {response.status_code}"
                raise RuntimeError(f"Failed refreshing MLX token: {detail}")

            try:
                data = response.json()
            except ValueError as exc:
                raise RuntimeError("Token refresh response was not valid JSON") from exc

            new_token = data.get("data", {}).get("token") if isinstance(data, Mapping) else None
            if not new_token:
                raise RuntimeError("Token refresh response missing token")

            self.token = str(new_token)
            logger.info("Multilogin token refreshed")
            return self.token

    async def resolve_folder_id(self, profile_id: str) -> str:
        resp = await self.request(
            "POST",
            "/profile/metas",
            upstream="mlx",
            json={"ids": [profile_id]},
        )

        profiles: list[dict[str, Any]] = []
        if isinstance(resp, Mapping):
            data = resp.get("data")
            if isinstance(data, Mapping):
                nested_profiles = data.get("profiles")
                if isinstance(nested_profiles, list):
                    profiles = [p for p in nested_profiles if isinstance(p, Mapping)]

            if not profiles:
                flat_profiles = resp.get("profiles")
                if isinstance(flat_profiles, list):
                    profiles = [p for p in flat_profiles if isinstance(p, Mapping)]

        profile = profiles[0] if profiles else None
        if profile is None:
            raise RuntimeError(f"Unable to resolve folder_id for profile {profile_id}")

        folder = profile.get("folder")
        metadata = profile.get("metadata")
        folder_id = (
            profile.get("folder_id")
            or profile.get("folderId")
            or (folder.get("id") if isinstance(folder, Mapping) else None)
            or (folder.get("_id") if isinstance(folder, Mapping) else None)
            or (metadata.get("folder_id") if isinstance(metadata, Mapping) else None)
        )
        if folder_id:
            return str(folder_id)

        raise RuntimeError("folder_id not found in profile metas response")

    async def start_profile(
        self,
        profile_id: str,
        folder_id: str | None = None,
    ) -> dict[str, Any]:
        if not self._settings.mlx_profile_start_path:
            raise RuntimeError(
                "MLX_PROFILE_START_PATH is not set. Configure it for your Multilogin deployment."
            )

        if folder_id is None:
            folder_id = self._settings.mlx_folder_id or await self.resolve_folder_id(profile_id)

        path = self._settings.mlx_profile_start_path.format(
            profile_id=profile_id,
            folder_id=folder_id,
        )
        path = f"{path}?{urlencode({'automation_type': 'playwright'})}"
        response = await self._request_profile_action(
            action="start",
            profile_id=profile_id,
            path_or_url=path,
        )
        return self._expect_json_object(response, action="start", profile_id=profile_id)

    async def stop_profile(self, profile_id: str) -> None:
        response = await self._request_profile_action(
            action="stop",
            profile_id=profile_id,
            path_or_url=self._settings.mlx_profile_stop_path,
        )
        if response.is_success or response.status_code == 204:
            return

        raise RuntimeError(
            f"Failed to stop profile '{profile_id}': {self._response_detail(response)}"
        )

    async def connect_playwright(self, *, ws_endpoint: str) -> tuple[Browser, BrowserContext]:
        if not ws_endpoint:
            raise ValueError("ws_endpoint must be a non-empty websocket URL")

        playwright = await self._get_playwright()
        browser = await playwright.chromium.connect_over_cdp(ws_endpoint)
        if not browser.contexts:
            await browser.close()
            raise RuntimeError("Connected browser did not expose any browser contexts")

        return browser, browser.contexts[0]

    async def open_page_for_profile(self, profile_id: str, target_url: str) -> Page:
        profile = await self.start_profile(profile_id)
        ws_endpoint = self._extract_ws_endpoint(profile)
        browser, context = await self.connect_playwright(ws_endpoint=ws_endpoint)
        page = await context.new_page()
        session = ManagedProfileSession(
            client=self,
            profile_id=profile_id,
            browser=browser,
            context=context,
            page=page,
        )
        self._remember_session(session)

        try:
            await page.goto(target_url, wait_until="domcontentloaded")
        except Exception:
            try:
                await session.aclose()
            except Exception:
                pass
            raise

        return page

    def session_for_page(self, page: Page) -> ManagedProfileSession | None:
        return self._sessions_by_page.get(id(page))

    def session_for_context(self, context: BrowserContext) -> ManagedProfileSession | None:
        return self._sessions_by_context.get(id(context))

    async def close_page(self, page: Page, *, stop_profile: bool = True) -> None:
        session = self.session_for_page(page)
        if session is None:
            if not page.is_closed():
                await page.close()
            return

        await session.aclose(stop_profile=stop_profile)

    async def _get_playwright(self) -> Playwright:
        if self._playwright is None:
            self._playwright = await async_playwright().start()
        return self._playwright

    async def _request_profile_action(
        self,
        *,
        action: str,
        profile_id: str,
        path_or_url: str,
    ) -> httpx.Response:
        if not path_or_url:
            raise RuntimeError(
                f"MLX_PROFILE_{action.upper()}_PATH is not set. Configure it for your Multilogin deployment."
            )

        method, url_or_path, payload = self._resolve_profile_request(
            path_or_url=path_or_url,
            profile_id=profile_id,
        )

        attempts = 0
        while True:
            try:
                response = await self._send_request(
                    method,
                    url_or_path,
                    upstream="launcher",
                    token=None,
                    params=None,
                    json=payload,
                    content=None,
                    headers=None,
                )
            except UpstreamRequestError as exc:
                raise RuntimeError(f"Failed to {action} profile '{profile_id}': {exc.detail}") from exc

            if response.is_success:
                return response

            error_code = self._response_error_code(response)
            if (
                action == "start"
                and error_code == "CORE_DOWNLOADING_STARTED"
                and attempts < CORE_DOWNLOAD_MAX_RETRIES
            ):
                attempts += 1
                logger.info(
                    "Multilogin core download in progress for profile '%s'; retrying start in %.1fs (%d/%d)",
                    profile_id,
                    CORE_DOWNLOAD_RETRY_DELAY_S,
                    attempts,
                    CORE_DOWNLOAD_MAX_RETRIES,
                )
                await asyncio.sleep(CORE_DOWNLOAD_RETRY_DELAY_S)
                continue

            break

        raise RuntimeError(
            f"Failed to {action} profile '{profile_id}': {self._response_detail(response)}"
        )

    def _resolve_profile_request(
        self,
        *,
        path_or_url: str,
        profile_id: str,
    ) -> tuple[str, str, dict[str, str] | None]:
        if "/profile/f/" in path_or_url and "/start" in path_or_url:
            return "GET", path_or_url, None

        if "{profile_id}" in path_or_url or "{profileId}" in path_or_url:
            return (
                "GET",
                path_or_url.format(profile_id=profile_id, profileId=profile_id),
                None,
            )

        return "POST", path_or_url, {"profile_id": profile_id}

    async def _send_request(
        self,
        method: str,
        url_or_path: str,
        *,
        upstream: str,
        token: str | None,
        params: list[tuple[str, str]] | None,
        json: object | None,
        content: bytes | None,
        headers: Mapping[str, str] | None,
    ) -> httpx.Response:
        response = await self._request_once(
            method,
            url_or_path,
            upstream=upstream,
            token=token,
            params=params,
            json=json,
            content=content,
            headers=headers,
        )
        if response.status_code != 401:
            return response

        await self.refresh_token()
        response = await self._request_once(
            method,
            url_or_path,
            upstream=upstream,
            token=token,
            params=params,
            json=json,
            content=content,
            headers=headers,
        )
        if response.status_code == 401:
            raise RuntimeError("Multilogin token invalid/expired even after refresh")
        return response

    async def _request_once(
        self,
        method: str,
        url_or_path: str,
        *,
        upstream: str,
        token: str | None,
        params: list[tuple[str, str]] | None,
        json: object | None,
        content: bytes | None,
        headers: Mapping[str, str] | None,
    ) -> httpx.Response:
        return await self._http.request(
            method,
            url_or_path,
            upstream=upstream,
            token=token or self.token,
            params=params,
            json=json,
            content=content,
            headers=headers,
        )

    def _extract_ws_endpoint(self, payload: Mapping[str, Any]) -> str:
        value: Any = payload
        for part in self._settings.mlx_ws_field.split("."):
            if not isinstance(value, Mapping) or part not in value:
                value = None
                break
            value = value[part]

        if isinstance(value, str) and value.strip():
            return value

        port = payload.get("port")
        if port is None and isinstance(payload.get("data"), Mapping):
            port = payload["data"].get("port")
        if port is None and isinstance(payload.get("value"), Mapping):
            port = payload["value"].get("port")

        if port is not None:
            return f"http://127.0.0.1:{port}"

        raise RuntimeError(
            f"Could not find websocket endpoint field '{self._settings.mlx_ws_field}' or a CDP port in start_profile response"
        )

    def _expect_json_object(
        self,
        response: httpx.Response,
        *,
        action: str,
        profile_id: str,
    ) -> dict[str, Any]:
        if not response.content:
            return {}

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"Failed to {action} profile '{profile_id}': expected JSON response"
            ) from exc

        if not isinstance(payload, dict):
            raise RuntimeError(
                f"Failed to {action} profile '{profile_id}': expected a JSON object response"
            )

        return payload

    def _response_detail(self, response: httpx.Response) -> str:
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                return str(response.json())
            except ValueError:
                pass

        text = response.text.strip()
        return text or f"upstream status {response.status_code}"

    def _response_error_code(self, response: httpx.Response) -> str | None:
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return None

        try:
            payload = response.json()
        except ValueError:
            return None

        if not isinstance(payload, Mapping):
            return None

        status = payload.get("status")
        if not isinstance(status, Mapping):
            return None

        error_code = status.get("error_code")
        if isinstance(error_code, str) and error_code:
            return error_code
        return None

    def _remember_session(self, session: ManagedProfileSession) -> None:
        if session.page is not None:
            self._sessions_by_page[id(session.page)] = session
        self._sessions_by_context[id(session.context)] = session

    def _forget_session(self, session: ManagedProfileSession) -> None:
        if session.page is not None:
            self._sessions_by_page.pop(id(session.page), None)
        self._sessions_by_context.pop(id(session.context), None)
