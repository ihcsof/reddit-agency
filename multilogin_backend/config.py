from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os

from dotenv import load_dotenv


load_dotenv()


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def _get_csv(name: str, default: str) -> tuple[str, ...]:
    raw_value = os.getenv(name, default)
    return tuple(part.strip() for part in raw_value.split(",") if part.strip())


@dataclass(frozen=True)
class Settings:
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = _get_int("APP_PORT", 8000)
    app_env: str = os.getenv("APP_ENV", "dev")
    app_cors_origins: tuple[str, ...] = _get_csv(
        "APP_CORS_ORIGINS",
        "http://127.0.0.1:3000,http://localhost:3000",
    )
    mlx_base_url: str = os.getenv("MLX_BASE_URL", "https://api.multilogin.com").rstrip("/")
    mlx_launcher_base_url: str = os.getenv(
        "MLX_LAUNCHER_BASE_URL",
        "https://launcher.mlx.yt:45001/api/v1",
    ).rstrip("/")
    mlx_token: str | None = os.getenv("MLX_TOKEN") or None
    mlx_timeout_s: int = _get_int("MLX_TIMEOUT_S", 30)
    mlx_profile_start_path: str = os.getenv("MLX_PROFILE_START_PATH", "").strip()
    mlx_profile_stop_path: str = os.getenv("MLX_PROFILE_STOP_PATH", "").strip()
    mlx_ws_field: str = os.getenv("MLX_WS_FIELD", "wsUrl").strip() or "wsUrl"
    mlx_webhook_secret: str = os.getenv("MLX_WEBHOOK_SECRET", "")
    airproxy_host: str = os.getenv("AIRPROXY_HOST", "s1.airproxy.io")
    airproxy_port: int = _get_int("AIRPROXY_PORT", 10306)
    airproxy_username: str = os.getenv("AIRPROXY_USERNAME", "interview_scouter")
    airproxy_password: str = os.getenv("AIRPROXY_PASSWORD", "")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
