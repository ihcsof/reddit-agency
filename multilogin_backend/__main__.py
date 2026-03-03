from __future__ import annotations

import uvicorn

from multilogin_backend.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "multilogin_backend.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_env == "dev",
    )


if __name__ == "__main__":
    main()
