from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse


router = APIRouter(tags=["frontend"])

FRONTEND_FILE = Path(__file__).resolve().parent.parent / "frontend" / "index.html"


@router.get("/", include_in_schema=False)
@router.get("/ui", include_in_schema=False)
async def frontend() -> FileResponse:
    return FileResponse(FRONTEND_FILE)
