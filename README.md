# Multilogin Console

This repository includes a static frontend, a FastAPI backend, and an automation runner:

- `frontend/`: static UI for local API interaction
- `multilogin_backend/`: FastAPI backend and upstream proxy routes
- `app/`: orchestration runner and UI automation helpers

## Local Run

Create a virtualenv and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
playwright install chromium
```

### Backend

Run the backend on `http://127.0.0.1:8000`:

```bash
python3 -m multilogin_backend
```

The backend serves the same static frontend at:

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/ui`

### Frontend

If you want to run the frontend separately while developing UI changes:

```bash
python3 -m http.server 3000 --directory frontend
```

Then open `http://127.0.0.1:3000` and set the UI's `Backend base URL` field to
`http://127.0.0.1:8000`.

The backend allows local CORS origins from `.env.example` via:

```env
APP_CORS_ORIGINS=http://127.0.0.1:3000,http://localhost:3000
```

## Environment

Important values in `.env`:

- `APP_HOST=0.0.0.0`
- `APP_PORT=8000`
- `APP_ENV=dev`
- `APP_CORS_ORIGINS=http://127.0.0.1:3000,http://localhost:3000`
- `MLX_BASE_URL=https://api.multilogin.com`
- `MLX_LAUNCHER_BASE_URL=https://launcher.mlx.yt:45001/api/v1`
- `MLX_TIMEOUT_S=30`
- `MLX_TOKEN=` optional default bearer token
- `MLX_PROFILE_START_PATH=` required for the lifecycle client
- `MLX_PROFILE_STOP_PATH=` required for the lifecycle client
- `MLX_WS_FIELD=wsUrl` field name or dotted path used to read the websocket URL
- `MLX_WEBHOOK_SECRET=` optional shared secret for `X-Webhook-Secret`
- `AIRPROXY_HOST=s1.airproxy.io`
- `AIRPROXY_PORT=10306`
- `AIRPROXY_USERNAME=interview_scouter`
- `AIRPROXY_PASSWORD=` required for `/airproxy/default-proxy`
- `AIRPROXY_CHANGE_IP_URL=` required for IP rotation in `python -m app.runner`
- `AIRPROXY_MIN_DEBOUNCE_S=5` minimum wait between AirProxy rotation and verification

The runner also requires `MLX_PROFILE_START_PATH`, `MLX_PROFILE_STOP_PATH`, and `MLX_WS_FIELD`
to be set correctly in `.env`, otherwise profile lifecycle start/stop and Playwright websocket
attachment will fail.

## API Routes

- `GET /health`
- `GET /`
- `GET /ui`
- `POST /mlx/auth/login`
- `POST /mlx/login`
- `POST /mlx/profile/login`
- `GET /mlx/proxy/user`
- `GET /mlx/proxy/fetch-data`
- `POST /mlx/profile/search`
- `POST /mlx/profile/metas`
- `ANY /mlx/raw/{path:path}`
- `ANY /launcher/raw/{path:path}`
- `GET /airproxy/default-proxy`
- `POST /airproxy/inject`
- `POST /mlx/webhooks/proxy-changed`
- `GET /mlx/webhooks/last-proxy-events`
- `POST /mlx/webhooks/refresh-proxy-state`

## Runner

Run the orchestration batch locally:

```bash
python3 -m app.runner \
  --target-url "https://www.reddit.com/r/test/comments/example/post/" \
  --profiles profile-001 profile-002 \
  --comments "First local run comment" "Second local run comment"
```

The runner uses the existing Multilogin and AirProxy settings from `.env`, enforces a global
`100` units per `60` seconds rate limit, and prints a JSON array of per-unit results.
