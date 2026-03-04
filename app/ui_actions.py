from __future__ import annotations

import asyncio

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Locator, Page, TimeoutError as PlaywrightTimeoutError

from app.selectors import (
    COMMENT_TRIGGER,
    COMMENT_SUBMIT,
    COMMENT_TEXTBOX,
    COPY_LINK_OPTION,
    SHARE_BUTTON,
    VOTE_BUTTON,
)


class ActionSkipped(RuntimeError):
    pass


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


async def first_or_skip(page: Page, selector: str, name: str) -> Locator:
    loc = page.locator(selector).first
    if await loc.count() == 0:
        raise ActionSkipped(f"{name} not found")
    return loc


async def ensure_comment_textbox(page: Page) -> Locator:
    textbox = page.locator(COMMENT_TEXTBOX).first
    if await textbox.count():
        try:
            await textbox.wait_for(state="visible", timeout=1_500)
            return textbox
        except PlaywrightTimeoutError:
            pass

    trigger = page.locator(COMMENT_TRIGGER).first
    if not await textbox.count() and not await trigger.count():
        raise ActionSkipped("comment box not found")
    if await trigger.count():
        await click_with_retry(trigger)
        await page.wait_for_timeout(500)

    if not await textbox.count():
        raise ActionSkipped("comment box not found")

    await textbox.wait_for(state="visible", timeout=5_000)
    return textbox


async def type_comment(page: Page, text: str) -> None:
    textbox = await ensure_comment_textbox(page)
    await fill_contenteditable(textbox, text)


async def submit_comment(page: Page) -> None:
    submit = await first_or_skip(page, COMMENT_SUBMIT, "comment submit")
    await click_with_retry(submit)


async def click_vote(page: Page) -> None:
    vote_button = await first_or_skip(page, VOTE_BUTTON, "vote button")
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
    share_button = await first_or_skip(page, SHARE_BUTTON, "share button")
    await click_with_retry(share_button)

    copy_container = await first_or_skip(page, COPY_LINK_OPTION, "copy link option")
    try:
        await copy_container.wait_for(state="visible", timeout=5_000)
    except PlaywrightTimeoutError:
        await click_with_retry(share_button)
        copy_container = await first_or_skip(page, COPY_LINK_OPTION, "copy link option")
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
    "ActionSkipped",
    "ensure_clickable",
    "ensure_comment_textbox",
    "fill_contenteditable",
    "first_or_skip",
    "submit_comment",
    "type_comment",
    "wait_for_hydration",
]
