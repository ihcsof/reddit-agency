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


@dataclass(frozen=True)
class Settings:
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = _get_int("APP_PORT", 8000)
    app_env: str = os.getenv("APP_ENV", "dev")
    mlx_base_url: str = os.getenv("MLX_BASE_URL", "https://api.multilogin.com").rstrip("/")
    mlx_launcher_base_url: str = os.getenv(
        "MLX_LAUNCHER_BASE_URL",
        "https://launcher.mlx.yt:45001/api/v1",
    ).rstrip("/")
    mlx_token: str = os.getenv("MLX_TOKEN", "")
    mlx_timeout_s: int = _get_int("MLX_TIMEOUT_S", 30)
    mlx_webhook_secret: str = os.getenv("MLX_WEBHOOK_SECRET", "")
    airproxy_host: str = os.getenv("AIRPROXY_HOST", "s1.airproxy.io")
    airproxy_port: int = _get_int("AIRPROXY_PORT", 10306)
    airproxy_username: str = os.getenv("AIRPROXY_USERNAME", "interview_scouter")
    airproxy_password: str = os.getenv("AIRPROXY_PASSWORD", "")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
