# Multilogin Backend

Small FastAPI backend that proxies the Multilogin X API and launcher API.

It also serves a very lightweight internal UI at `/` and `/ui` for local interaction with the exposed routes.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn multilogin_backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Then open `http://127.0.0.1:8000/`.

## Environment

Copy `.env.example` to `.env` and set any secrets you need:

- `MLX_TOKEN` is optional at startup and used as a default bearer token.
- `AIRPROXY_PASSWORD` is required only for the Airproxy helper endpoint.

## Routes

- `GET /health`
- `GET /`
- `GET /ui`
- `POST /mlx/user/signin`
- `POST /mlx/user/refresh-token`
- `GET /mlx/user/workspaces`
- `GET /mlx/workspace/automation-token`
- `ANY /mlx/{path:path}`
- `GET /launcher/profile/f/{folder_id}/p/{profile_id}/start`
- `GET /launcher/profile/status/p/{profile_id}`
- `GET /launcher/profile/stop/p/{profile_id}`
- `POST /launcher/profile/quick`
- `ANY /launcher/{path:path}`
- `GET /airproxy/proxy`
