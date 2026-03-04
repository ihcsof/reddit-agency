from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.runner import run_batch


router = APIRouter(prefix="/runner", tags=["runner"])


class RunnerBatchRequest(BaseModel):
    target_url: str
    profiles: list[str]
    comments: list[str]


@router.post("/run")
async def run_runner_batch(payload: RunnerBatchRequest):
    profile_ids = [value.strip() for value in payload.profiles if value.strip()]
    comments = [value.strip() for value in payload.comments if value.strip()]
    target_url = payload.target_url.strip()

    if not target_url:
        raise HTTPException(status_code=400, detail="target_url is required")
    if not profile_ids:
        raise HTTPException(status_code=400, detail="At least one profile is required")
    if not comments:
        raise HTTPException(status_code=400, detail="At least one comment is required")
    if len(profile_ids) != len(comments):
        raise HTTPException(
            status_code=400,
            detail="profiles and comments must contain the same number of entries",
        )

    return await run_batch(
        target_url=target_url,
        profile_ids=profile_ids,
        comments=comments,
    )
