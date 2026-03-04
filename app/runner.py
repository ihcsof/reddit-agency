from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from app.rate_limiter import OperationRateLimiter

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Page
    from multilogin_backend.multilogin_client import MultiloginClient
    from multilogin_backend.services.airproxy_client import AirProxyClient


GLOBAL_RATE_LIMITER = OperationRateLimiter(limit=100, window_s=60.0)


def _iso_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _build_error(step: str, exc: Exception) -> dict[str, str]:
    return {
        "step": step,
        "message": str(exc),
        "exception_type": type(exc).__name__,
    }


def _origin_for_url(target_url: str) -> str | None:
    parts = urlsplit(target_url)
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


def _extract_ws_endpoint(payload: Mapping[str, Any]) -> str:
    from multilogin_backend.config import get_settings

    settings = get_settings()
    value: Any = payload

    for part in settings.mlx_ws_field.split("."):
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
        f"Could not find websocket endpoint field '{settings.mlx_ws_field}' or a CDP port in start_profile response"
    )


async def _close_profile_resources(
    *,
    multilogin: "MultiloginClient",
    profile_id: str,
    page: "Page | None",
    context: "BrowserContext | None",
    browser: "Browser | None",
    profile_started: bool,
) -> Exception | None:
    first_error: Exception | None = None

    if page is not None and not page.is_closed():
        try:
            await page.close()
        except Exception as exc:
            first_error = first_error or exc

    if context is not None:
        try:
            await context.close()
        except Exception as exc:
            first_error = first_error or exc

    if browser is not None:
        try:
            await browser.close()
        except Exception as exc:
            first_error = first_error or exc

    if profile_started:
        try:
            await multilogin.stop_profile(profile_id)
        except Exception as exc:
            first_error = first_error or exc

    return first_error


async def _run_unit(
    *,
    limiter: OperationRateLimiter,
    airproxy: "AirProxyClient",
    multilogin: "MultiloginClient",
    profile_id: str,
    target_url: str,
    comment_text: str,
) -> dict[str, Any]:
    from app.ui_actions import (
        ActionSkipped,
        click_share_and_copy_link,
        click_vote,
        submit_comment,
        type_comment,
        wait_for_hydration,
    )
    from multilogin_backend.config import get_settings

    started_at = _iso_timestamp()
    steps = {
        "rotate_ip": "skip",
        "comment": "fail",
        "vote": "fail",
        "share": "fail",
    }
    result: dict[str, Any] = {
        "profile_id": profile_id,
        "target_url": target_url,
        "steps": steps,
        "started_at": started_at,
        "finished_at": started_at,
        "error": None,
        "skipped": False,
    }

    browser: Browser | None = None
    context: BrowserContext | None = None
    page: Page | None = None
    clipboard_text: str | None = None
    error: dict[str, str] | None = None
    profile_started = False
    current_step = "rotate_ip"

    try:
        await limiter.acquire()

        rotation = await airproxy.rotate_ip_and_verify(
            min_debounce_s=get_settings().airproxy_min_debounce_s,
            max_retries=1,
        )
        if rotation.get("status") == "skipped":
            steps["rotate_ip"] = "skip"
            steps["comment"] = "skip"
            steps["vote"] = "skip"
            steps["share"] = "skip"
            result["error"] = None
            result["skipped"] = True
            result["skip_reason"] = str(rotation.get("reason") or "ip_not_changed")
            return result

        steps["rotate_ip"] = "ok"

        current_step = "open_profile"
        profile = await multilogin.start_profile(profile_id)
        profile_started = True
        ws_endpoint = _extract_ws_endpoint(profile)
        browser, context = await multilogin.connect_playwright(ws_endpoint=ws_endpoint)

        origin = _origin_for_url(target_url)
        if origin is not None:
            try:
                await context.grant_permissions(
                    ["clipboard-read", "clipboard-write"],
                    origin=origin,
                )
            except Exception:
                pass

        page = await context.new_page()
        await page.goto(target_url, wait_until="domcontentloaded")
        await wait_for_hydration(page)

        current_step = "comment"
        try:
            await type_comment(page, comment_text)
            await submit_comment(page)
            steps["comment"] = "ok"
        except ActionSkipped:
            steps["comment"] = "skip"

        current_step = "vote"
        try:
            await click_vote(page)
            steps["vote"] = "ok"
        except ActionSkipped:
            steps["vote"] = "skip"

        current_step = "share"
        try:
            clipboard_text = await click_share_and_copy_link(page)
            steps["share"] = "ok"
        except ActionSkipped:
            steps["share"] = "skip"
    except Exception as exc:
        error = _build_error(current_step, exc)
    finally:
        cleanup_error = await _close_profile_resources(
            multilogin=multilogin,
            profile_id=profile_id,
            page=page,
            context=context,
            browser=browser,
            profile_started=profile_started,
        )
        if error is None and cleanup_error is not None:
            error = _build_error("close_profile", cleanup_error)

        result["finished_at"] = _iso_timestamp()
        if clipboard_text is not None:
            result["clipboard_text"] = clipboard_text
        if error is not None:
            result["error"] = error

    return result


async def run_unit(profile_id: str, target_url: str, comment_text: str) -> dict[str, Any]:
    from multilogin_backend.multilogin_client import MultiloginClient
    from multilogin_backend.services.airproxy_client import AirProxyClient

    airproxy = AirProxyClient()
    multilogin = MultiloginClient()
    try:
        return await _run_unit(
            limiter=GLOBAL_RATE_LIMITER,
            airproxy=airproxy,
            multilogin=multilogin,
            profile_id=profile_id,
            target_url=target_url,
            comment_text=comment_text,
        )
    finally:
        await multilogin.aclose()
        await airproxy.aclose()


async def run_batch(
    target_url: str,
    profile_ids: list[str],
    comments: list[str],
) -> list[dict[str, Any]]:
    from multilogin_backend.multilogin_client import MultiloginClient
    from multilogin_backend.services.airproxy_client import AirProxyClient

    if len(profile_ids) < len(comments):
        raise ValueError("profile_ids must contain at least as many entries as comments")

    airproxy = AirProxyClient()
    multilogin = MultiloginClient()
    results: list[dict[str, Any]] = []

    try:
        for profile_id, comment_text in zip(profile_ids, comments, strict=False):
            result = await _run_unit(
                limiter=GLOBAL_RATE_LIMITER,
                airproxy=airproxy,
                multilogin=multilogin,
                profile_id=profile_id,
                target_url=target_url,
                comment_text=comment_text,
            )
            results.append(result)
    finally:
        await multilogin.aclose()
        await airproxy.aclose()

    return results


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run comment/vote/share automation batch")
    parser.add_argument("--target-url", required=True, help="Target page URL")
    parser.add_argument(
        "--profiles",
        nargs="+",
        required=True,
        help="Ordered profile IDs to use for the batch",
    )
    parser.add_argument(
        "--comments",
        nargs="+",
        required=True,
        help="Ordered comment texts to post",
    )
    return parser


async def _async_main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    results = await run_batch(
        target_url=args.target_url,
        profile_ids=list(args.profiles),
        comments=list(args.comments),
    )
    print(json.dumps(results, indent=2))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(_async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
