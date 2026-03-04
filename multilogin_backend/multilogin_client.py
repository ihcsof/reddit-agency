from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

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
        self._playwright: Playwright | None = None
        self._sessions_by_page: dict[int, ManagedProfileSession] = {}
        self._sessions_by_context: dict[int, ManagedProfileSession] = {}

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
        response = await self._http.request(
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

    async def get_profiles(self) -> list[dict]:
        resp = await self.request("GET", "/profile", upstream="mlx")
        if isinstance(resp, dict):
            data = resp.get("data", []) or resp.get("profiles", [])
            return data if isinstance(data, list) else []
        return resp if isinstance(resp, list) else []

    async def resolve_folder_id(self, profile_id: str) -> str:
        profiles = await self.get_profiles()

        for p in profiles:
            if not isinstance(p, Mapping):
                continue
            if p.get("id") == profile_id:
                folder = p.get("folder")
                folder_id = (
                    p.get("folder_id")
                    or p.get("folderId")
                    or (folder.get("id") if isinstance(folder, Mapping) else None)
                )
                if folder_id:
                    return str(folder_id)

        raise RuntimeError(f"Unable to resolve folder_id for profile {profile_id}")

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
            folder_id = await self.resolve_folder_id(profile_id)

        path = self._settings.mlx_profile_start_path.format(
            profile_id=profile_id,
            folder_id=folder_id,
        )
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

        try:
            response = await self._http.request(
                method,
                url_or_path,
                upstream="launcher",
                json=payload,
            )
        except UpstreamRequestError as exc:
            raise RuntimeError(f"Failed to {action} profile '{profile_id}': {exc.detail}") from exc

        if response.is_success:
            return response

        raise RuntimeError(
            f"Failed to {action} profile '{profile_id}': {self._response_detail(response)}"
        )

    def _resolve_profile_request(
        self,
        *,
        path_or_url: str,
        profile_id: str,
    ) -> tuple[str, str, dict[str, str] | None]:
        if "{profile_id}" in path_or_url or "{profileId}" in path_or_url:
            return (
                "GET",
                path_or_url.format(profile_id=profile_id, profileId=profile_id),
                None,
            )

        return "POST", path_or_url, {"profile_id": profile_id}

    def _extract_ws_endpoint(self, payload: Mapping[str, Any]) -> str:
        value: Any = payload
        for part in self._settings.mlx_ws_field.split("."):
            if not isinstance(value, Mapping) or part not in value:
                raise RuntimeError(
                    f"Could not find websocket endpoint field '{self._settings.mlx_ws_field}' in start_profile response"
                )
            value = value[part]

        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(
                f"Start profile response field '{self._settings.mlx_ws_field}' did not contain a websocket URL"
            )

        return value

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

    def _remember_session(self, session: ManagedProfileSession) -> None:
        if session.page is not None:
            self._sessions_by_page[id(session.page)] = session
        self._sessions_by_context[id(session.context)] = session

    def _forget_session(self, session: ManagedProfileSession) -> None:
        if session.page is not None:
            self._sessions_by_page.pop(id(session.page), None)
        self._sessions_by_context.pop(id(session.context), None)
