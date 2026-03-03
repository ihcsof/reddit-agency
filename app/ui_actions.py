from __future__ import annotations

import asyncio

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Locator, Page, TimeoutError as PlaywrightTimeoutError

from app.selectors import (
    COMMENT_SUBMIT,
    COMMENT_TEXTBOX,
    COPY_LINK_OPTION,
    SHARE_BUTTON,
    VOTE_BUTTON,
)


async def wait_for_hydration(page: Page) -> None:
    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_timeout(350)


async def ensure_clickable(locator: Locator) -> Locator:
    self_clickable = locator.locator("xpath=self::button | self::*[@role='button']").first
    if await self_clickable.count():
        return self_clickable

    ancestor_button = locator.locator("xpath=ancestor::button[1]").first
    if await ancestor_button.count():
        return ancestor_button

    ancestor_role_button = locator.locator("xpath=ancestor::*[@role='button'][1]").first
    if await ancestor_role_button.count():
        return ancestor_role_button

    return locator


async def click_with_retry(locator: Locator, tries: int = 3, delay_s: float = 0.5) -> None:
    last_error: Exception | None = None
    target = await ensure_clickable(locator)

    for attempt in range(tries):
        try:
            await target.wait_for(state="visible", timeout=2_500)
            await target.scroll_into_view_if_needed(timeout=2_500)
            await target.click(timeout=2_500, force=attempt == tries - 1)
            return
        except (PlaywrightError, PlaywrightTimeoutError) as exc:
            last_error = exc
            if attempt == tries - 1:
                break
            await asyncio.sleep(delay_s)

    if last_error is not None:
        raise last_error


async def fill_contenteditable(locator: Locator, text: str) -> None:
    await locator.wait_for(state="visible", timeout=5_000)
    await click_with_retry(locator)

    try:
        await locator.press("ControlOrMeta+A")
        await locator.press("Backspace")
    except (PlaywrightError, PlaywrightTimeoutError):
        pass

    try:
        await locator.type(text, delay=20)
    except (PlaywrightError, PlaywrightTimeoutError):
        await locator.evaluate(
            """(node, value) => {
                node.textContent = value;
                node.dispatchEvent(new InputEvent("input", { bubbles: true, data: value }));
                node.dispatchEvent(new Event("change", { bubbles: true }));
            }""",
            text,
        )


async def type_comment(page: Page, text: str) -> None:
    textbox = page.locator(COMMENT_TEXTBOX).first
    await fill_contenteditable(textbox, text)


async def submit_comment(page: Page) -> None:
    submit = page.locator(COMMENT_SUBMIT).first
    await click_with_retry(submit)


async def click_vote(page: Page) -> None:
    vote_button = page.locator(VOTE_BUTTON).first
    await vote_button.wait_for(state="visible", timeout=5_000)
    previous_state = await vote_button.get_attribute("aria-pressed")

    await click_with_retry(vote_button)

    if previous_state == "false":
        try:
            await vote_button.evaluate(
                """async (node) => {
                    const deadline = Date.now() + 2000;
                    while (Date.now() < deadline) {
                        if (node.getAttribute("aria-pressed") === "true") {
                            return true;
                        }
                        await new Promise((resolve) => setTimeout(resolve, 100));
                    }
                    return false;
                }"""
            )
        except (PlaywrightError, PlaywrightTimeoutError):
            pass


async def click_share_and_copy_link(page: Page) -> str | None:
    share_button = page.locator(SHARE_BUTTON).first
    await click_with_retry(share_button)

    copy_container = page.locator(COPY_LINK_OPTION).first
    try:
        await copy_container.wait_for(state="visible", timeout=5_000)
    except PlaywrightTimeoutError:
        await click_with_retry(share_button)
        await copy_container.wait_for(state="visible", timeout=5_000)

    copy_option = copy_container.locator('[role="menuitem"]').first
    if await copy_option.count():
        await click_with_retry(await ensure_clickable(copy_option))
    else:
        await click_with_retry(await ensure_clickable(copy_container))

    await page.wait_for_timeout(200)

    try:
        return await page.evaluate("navigator.clipboard.readText()")
    except (PlaywrightError, PlaywrightTimeoutError):
        return None


__all__ = [
    "click_share_and_copy_link",
    "click_vote",
    "click_with_retry",
    "ensure_clickable",
    "fill_contenteditable",
    "submit_comment",
    "type_comment",
    "wait_for_hydration",
]
