from __future__ import annotations

from html import escape
from urllib.parse import urljoin, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from multilogin_backend.playwright_runtime import DemoAutomationRuntime
from multilogin_backend.routers.deps import get_demo_runtime


router = APIRouter(prefix="/demo", tags=["demo"])


class DemoBatchRequest(BaseModel):
    content_url: str = Field(min_length=1)
    comments: list[str] = Field(min_length=1)
    profile_ids: list[str] = Field(min_length=1)
    headless: bool = True

def _resolve_local_content_url(request: Request, content_url: str) -> str:
    normalized = content_url.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="content_url is required")

    if normalized.startswith("/"):
        resolved = urljoin(str(request.base_url), normalized.lstrip("/"))
    else:
        resolved = normalized

    parsed = urlsplit(resolved)
    request_host = request.url.hostname
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="content_url must be http or https")
    if parsed.path.startswith("/demo/content/") is False:
        raise HTTPException(
            status_code=400,
            detail="demo runner only accepts self-hosted /demo/content/* pages",
        )
    if parsed.hostname not in {request_host, "127.0.0.1", "localhost"}:
        raise HTTPException(
            status_code=400,
            detail="demo runner only accepts content hosted on this local app",
        )
    return resolved


@router.post("/batch-run")
async def run_demo_batch(
    payload: DemoBatchRequest,
    request: Request,
    runtime: DemoAutomationRuntime = Depends(get_demo_runtime),
) -> dict[str, object]:
    comments = [comment.strip() for comment in payload.comments if comment.strip()]
    profile_ids = [profile_id.strip() for profile_id in payload.profile_ids if profile_id.strip()]
    if len(profile_ids) < len(comments):
        raise HTTPException(
            status_code=400,
            detail="profile_ids must contain at least as many non-empty values as comments",
        )

    try:
        return await runtime.run_batch(
            content_url=_resolve_local_content_url(request, payload.content_url),
            comments=comments,
            profile_ids=profile_ids,
            headless=payload.headless,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/content/{content_id}", response_class=HTMLResponse)
async def demo_content(content_id: str) -> HTMLResponse:
    safe_content_id = escape(content_id)
    html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Demo Content {safe_content_id}</title>
    <style>
      :root {{
        --paper: #f8f3ea;
        --panel: rgba(255, 255, 255, 0.92);
        --ink: #191512;
        --muted: #685f56;
        --line: #d7ccbc;
        --accent: #b34c26;
        --accent-strong: #8f3d1d;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        min-height: 100vh;
        color: var(--ink);
        font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
        background:
          radial-gradient(circle at top left, rgba(179, 76, 38, 0.12), transparent 24%),
          radial-gradient(circle at bottom right, rgba(33, 82, 115, 0.14), transparent 26%),
          linear-gradient(180deg, #fbf7f0 0%, #f0e6d8 100%);
      }}
      main {{
        max-width: 760px;
        margin: 0 auto;
        padding: 36px 18px 48px;
      }}
      article {{
        border: 1px solid var(--line);
        border-radius: 24px;
        padding: 24px;
        background: var(--panel);
        box-shadow: 0 20px 44px rgba(37, 28, 18, 0.08);
      }}
      h1 {{
        margin: 0 0 10px;
        font-size: clamp(2rem, 5vw, 3rem);
        font-family: "Iowan Old Style", "Palatino Linotype", serif;
        line-height: 1.02;
      }}
      p {{
        color: var(--muted);
        line-height: 1.6;
      }}
      .toolbar {{
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
        margin: 18px 0 22px;
      }}
      button {{
        border: 0;
        border-radius: 999px;
        padding: 10px 14px;
        background: #ece0d4;
        color: var(--ink);
        font: inherit;
        font-weight: 600;
        cursor: pointer;
      }}
      button.primary {{
        background: var(--accent);
        color: white;
      }}
      .composer {{
        display: grid;
        gap: 10px;
        margin: 18px 0 14px;
        padding: 16px;
        border: 1px solid var(--line);
        border-radius: 18px;
        background: #fffaf4;
      }}
      .textbox {{
        min-height: 72px;
        border: 1px solid var(--line);
        border-radius: 14px;
        padding: 12px;
        background: white;
        outline: none;
      }}
      .list {{
        display: grid;
        gap: 10px;
      }}
      .comment {{
        padding: 12px 14px;
        border-radius: 14px;
        background: #fff;
        border: 1px solid var(--line);
      }}
      .meta {{
        display: inline-flex;
        gap: 8px;
        align-items: center;
        padding: 6px 10px;
        border-radius: 999px;
        border: 1px solid var(--line);
        color: var(--muted);
      }}
      .share-menu {{
        margin-top: 8px;
        padding: 8px;
        border: 1px solid var(--line);
        border-radius: 16px;
        background: white;
      }}
      .hidden {{ display: none; }}
      .overlay {{
        position: fixed;
        inset: 0;
        display: grid;
        place-items: center;
        background: rgba(21, 18, 14, 0.55);
        padding: 16px;
      }}
      .modal {{
        max-width: 440px;
        padding: 20px;
        border-radius: 20px;
        background: white;
        border: 1px solid var(--line);
      }}
    </style>
  </head>
  <body>
    <div class="overlay" id="consentOverlay">
      <div class="modal">
        <h2>Demo Consent</h2>
        <p>This page intentionally mimics a hydrated social post so the local Playwright runner has a safe target.</p>
        <button class="primary" data-testid="consent-accept">Accept</button>
      </div>
    </div>
    <main>
      <article data-testid="demo-post">
        <span class="meta">Demo content id: {safe_content_id}</span>
        <h1>Self-hosted interaction target</h1>
        <p>
          This page is local to the FastAPI app. It exposes stable controls for comment, upvote,
          and copy-link actions so the demo runner can be exercised without touching external sites.
        </p>

        <div class="toolbar">
          <button data-testid="upvote" upvote aria-pressed="false">Upvote</button>
          <button data-testid="share-open">Share</button>
        </div>

        <div class="share-menu hidden" id="shareMenu">
          <button class="primary share-menu-copy-link-option" data-testid="share-copy-link">Copy link</button>
          <span class="meta" id="shareStatus">Waiting</span>
        </div>

        <section class="composer">
          <div
            class="textbox"
            data-testid="comment-box"
            contenteditable="true"
            role="textbox"
            aria-label="Write a comment"
          ></div>
          <div class="toolbar">
            <button class="primary" data-testid="comment-submit" slot="submit-button" type="button">Comment</button>
          </div>
        </section>

        <section>
          <h2>Comments</h2>
          <div class="list" data-testid="comment-list"></div>
        </section>
      </article>
    </main>
    <script>
      const consentOverlay = document.getElementById("consentOverlay");
      const commentBox = document.querySelector("[data-testid='comment-box']");
      const commentList = document.querySelector("[data-testid='comment-list']");
      const submitButton = document.querySelector("[data-testid='comment-submit']");
      const upvoteButton = document.querySelector("[data-testid='upvote']");
      const shareOpenButton = document.querySelector("[data-testid='share-open']");
      const shareCopyButton = document.querySelector("[data-testid='share-copy-link']");
      const shareMenu = document.getElementById("shareMenu");
      const shareStatus = document.getElementById("shareStatus");

      document.querySelector("[data-testid='consent-accept']").addEventListener("click", () => {{
        consentOverlay.remove();
      }});

      submitButton.addEventListener("click", () => {{
        const text = commentBox.textContent.trim();
        if (!text) {{
          return;
        }}

        const item = document.createElement("div");
        item.className = "comment";
        item.setAttribute("data-testid", "comment-item");
        item.textContent = text;
        commentList.prepend(item);
        commentBox.textContent = "";
      }});

      upvoteButton.addEventListener("click", () => {{
        upvoteButton.setAttribute(
          "aria-pressed",
          upvoteButton.getAttribute("aria-pressed") === "true" ? "false" : "true"
        );
      }});

      shareOpenButton.addEventListener("click", () => {{
        shareMenu.classList.toggle("hidden");
      }});

      shareCopyButton.addEventListener("click", async () => {{
        try {{
          await navigator.clipboard.writeText(window.location.href);
          shareStatus.textContent = "Copied";
        }} catch (error) {{
          shareStatus.textContent = "Clipboard blocked";
        }}
      }});
    </script>
  </body>
</html>"""
    return HTMLResponse(html)
