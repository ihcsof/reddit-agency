from __future__ import annotations

import asyncio
import random
from collections import deque
from dataclasses import asdict, dataclass
from time import monotonic
from typing import Any
from urllib.parse import urlsplit

from playwright.async_api import Browser, Error as PlaywrightError, Page, async_playwright


def describe_runtime() -> str:
    return (
        "Demo Playwright runtime for local comment/upvote/share simulations. "
        "It is restricted to the app's self-hosted demo content routes."
    )


@dataclass(slots=True)
class DemoIpRotationResult:
    old_ip: str | None
    new_ip: str | None
    changed: bool
    attempts: int
    verification_method: str


@dataclass(slots=True)
class DemoProfileResult:
    profile_id: str
    comment: str
    status: str
    failed_step: str | None
    message: str
    ip_rotation: DemoIpRotationResult
    copied_link: str | None = None


class OperationRateLimiter:
    def __init__(self, *, limit: int, window_s: float) -> None:
        self._limit = limit
        self._window_s = window_s
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            wait_for = 0.0
            async with self._lock:
                now = monotonic()
                self._trim(now)
                if len(self._timestamps) < self._limit:
                    self._timestamps.append(now)
                    return
                wait_for = self._window_s - (now - self._timestamps[0])

            await asyncio.sleep(max(wait_for, 0.05))

    def _trim(self, now: float) -> None:
        while self._timestamps and now - self._timestamps[0] >= self._window_s:
            self._timestamps.popleft()


class DemoIpRotator:
    def __init__(self, *, debounce_s: float = 5.0) -> None:
        self._debounce_s = debounce_s
        self._counter = 0
        self._lock = asyncio.Lock()

    async def rotate(self, previous_ip: str | None) -> DemoIpRotationResult:
        first_ip = await self._change_ip()
        if first_ip != previous_ip:
            return DemoIpRotationResult(
                old_ip=previous_ip,
                new_ip=first_ip,
                changed=True,
                attempts=1,
                verification_method="simulated-change-ip",
            )

        second_ip = await self._change_ip()
        return DemoIpRotationResult(
            old_ip=previous_ip,
            new_ip=second_ip,
            changed=second_ip != previous_ip,
            attempts=2,
            verification_method="simulated-change-ip",
        )

    async def _change_ip(self) -> str:
        async with self._lock:
            self._counter += 1
            next_octet = ((self._counter - 1) % 200) + 1
            rotated_ip = f"198.51.100.{next_octet}"

        await asyncio.sleep(self._debounce_s)
        return rotated_ip


class DemoAutomationRuntime:
    def __init__(self) -> None:
        self._playwright = None
        self._rate_limiter = OperationRateLimiter(limit=100, window_s=60.0)
        self._ip_rotator = DemoIpRotator()

    async def aclose(self) -> None:
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    async def run_batch(
        self,
        *,
        content_url: str,
        comments: list[str],
        profile_ids: list[str],
        headless: bool = True,
    ) -> dict[str, Any]:
        if len(profile_ids) < len(comments):
            raise ValueError("profile_ids must contain at least as many entries as comments")
        if not comments:
            raise ValueError("comments must contain at least one entry")

        playwright = await self._get_playwright()
        results: list[DemoProfileResult] = []
        previous_ip: str | None = None

        for profile_id, comment in zip(profile_ids, comments, strict=False):
            await self._rate_limiter.acquire()
            result = await self._run_profile(
                playwright=playwright,
                content_url=content_url,
                profile_id=profile_id,
                comment_text=comment,
                previous_ip=previous_ip,
                headless=headless,
            )
            results.append(result)
            if result.ip_rotation.changed:
                previous_ip = result.ip_rotation.new_ip

        return {
            "content_url": content_url,
            "headless": headless,
            "requested_comments": len(comments),
            "processed_profiles": len(results),
            "results": [asdict(result) for result in results],
        }

    async def _get_playwright(self):
        if self._playwright is None:
            self._playwright = await async_playwright().start()
        return self._playwright

    async def _run_profile(
        self,
        *,
        playwright,
        content_url: str,
        profile_id: str,
        comment_text: str,
        previous_ip: str | None,
        headless: bool,
    ) -> DemoProfileResult:
        rotation = await self._ip_rotator.rotate(previous_ip)
        if not rotation.changed:
            return DemoProfileResult(
                profile_id=profile_id,
                comment=comment_text,
                status="skipped",
                failed_step="rotate_ip",
                message="IP did not change after one retry.",
                ip_rotation=rotation,
            )

        browser: Browser | None = None
        try:
            browser = await playwright.chromium.launch(headless=headless)
            context = await browser.new_context()
            origin = self._origin_for_url(content_url)
            await context.grant_permissions(["clipboard-read", "clipboard-write"], origin=origin)
            page = await context.new_page()

            await self._open_content(page, content_url)
            await self._post_comment(page, comment_text)
            await self._apply_upvote(page)
            copied_link = await self._copy_link(page)
            await page.wait_for_timeout(random.uniform(500, 2000))
            await context.close()

            return DemoProfileResult(
                profile_id=profile_id,
                comment=comment_text,
                status="success",
                failed_step=None,
                message="Completed comment, upvote, and copy-link flow.",
                ip_rotation=rotation,
                copied_link=copied_link,
            )
        except Exception as exc:
            failed_step = self._infer_failed_step(exc)
            return DemoProfileResult(
                profile_id=profile_id,
                comment=comment_text,
                status="failed",
                failed_step=failed_step,
                message=str(exc),
                ip_rotation=rotation,
            )
        finally:
            if browser is not None:
                await browser.close()

    async def _open_content(self, page: Page, content_url: str) -> None:
        await page.goto(content_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(450)
        consent_button = page.locator("[data-testid='consent-accept']")
        if await consent_button.count():
            try:
                await consent_button.first.click(timeout=800)
                await page.wait_for_timeout(150)
            except PlaywrightError:
                pass

        await page.locator("[data-testid='demo-post']").wait_for(timeout=5_000)

    async def _post_comment(self, page: Page, comment_text: str) -> None:
        composer = page.locator(
            "[data-testid='comment-box'], [contenteditable='true'][role='textbox']"
        ).first
        await composer.wait_for(timeout=5_000)
        await composer.click()
        await composer.fill(comment_text)

        submit = page.locator(
            "[data-testid='comment-submit'], [slot='submit-button'], button[type='submit']"
        ).first
        await submit.click()
        await page.locator("[data-testid='comment-item']").filter(has_text=comment_text).first.wait_for(
            timeout=5_000
        )

    async def _apply_upvote(self, page: Page) -> None:
        upvote = page.locator(
            "[data-testid='upvote'], [upvote], button[aria-pressed]"
        ).first
        await upvote.wait_for(timeout=5_000)
        if await upvote.get_attribute("aria-pressed") != "true":
            await upvote.click()
        await page.wait_for_function(
            """
            (selector) => {
              const node = document.querySelector(selector);
              return node && node.getAttribute("aria-pressed") === "true";
            }
            """,
            "[data-testid='upvote']",
            timeout=5_000,
        )

    async def _copy_link(self, page: Page) -> str | None:
        share_open = page.locator("[data-testid='share-open']").first
        await share_open.wait_for(timeout=5_000)
        await share_open.click()

        copy_link = page.locator(
            "[data-testid='share-copy-link'], .share-menu-copy-link-option"
        ).first
        await copy_link.wait_for(timeout=5_000)
        await copy_link.click()
        await page.wait_for_timeout(200)

        try:
            return await page.evaluate("async () => navigator.clipboard.readText()")
        except PlaywrightError:
            return None

    def _origin_for_url(self, url: str) -> str:
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}"

    def _infer_failed_step(self, exc: Exception) -> str:
        message = str(exc).lower()
        if "comment" in message or "textbox" in message or "submit" in message:
            return "comment"
        if "upvote" in message or "aria-pressed" in message:
            return "upvote"
        if "clipboard" in message or "share" in message or "copy" in message:
            return "share"
        if "goto" in message or "navigation" in message or "timeout" in message:
            return "open_profile"
        return "unknown"
