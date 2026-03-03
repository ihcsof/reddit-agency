# Multilogin API Proxy

Small FastAPI backend that proxies the Multilogin X API and launcher API, with a very lightweight
internal frontend at `/` and `/ui` for local interaction.

Playwright stays installed and ready for later Multilogin-driven browser automation work.
The backend is isolated from any scraper startup logic and does not require `SIDESHIFT_*` env vars.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m multilogin_backend
```

Then open `http://127.0.0.1:8000/`.

## Environment

Important variables in `.env`:

- `APP_HOST=0.0.0.0`
- `APP_PORT=8000`
- `APP_ENV=dev`
- `MLX_BASE_URL=https://api.multilogin.com`
- `MLX_LAUNCHER_BASE_URL=https://launcher.mlx.yt:45001/api/v1`
- `MLX_TIMEOUT_S=30`
- `MLX_TOKEN=` optional default bearer token
- `MLX_WEBHOOK_SECRET=` optional shared secret for `X-Webhook-Secret`
- `AIRPROXY_HOST=s1.airproxy.io`
- `AIRPROXY_PORT=10306`
- `AIRPROXY_USERNAME=interview_scouter`
- `AIRPROXY_PASSWORD=` required for `/airproxy/default-proxy`

## Routes

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

## Examples

Health:

```bash
curl http://localhost:8000/health
```

Profile login using the exact Multilogin doc flow:

```bash
curl -X POST http://localhost:8000/mlx/login \
  -H "Content-Type: application/json" \
  -d '{"profile_id":"<profile-id>","password":"<password>","password_is_md5":false}'
```

Fetch proxy data from the Multilogin proxy endpoint:

```bash
curl -H "X-MLX-Token: <token>" \
  http://localhost:8000/mlx/proxy/user
```

Profile search wrapper:

```bash
curl -X POST http://localhost:8000/mlx/profile/search \
  -H "Content-Type: application/json" \
  -H "X-MLX-Token: <token>" \
  -d '{"limit":20,"offset":0,"search_text":"","storage_type":"all","order_by":"created_at","sort":"asc"}'
```

Raw passthrough:

```bash
curl -X POST http://localhost:8000/mlx/raw/profile/search \
  -H "Content-Type: application/json" \
  -H "X-MLX-Token: <token>" \
  -d '{"limit":10,"offset":0}'
```

Launcher passthrough:

```bash
curl -H "X-MLX-Token: <token>" \
  http://localhost:8000/launcher/raw/api/v1/version
```

Webhook test:

```bash
curl -X POST http://localhost:8000/mlx/webhooks/proxy-changed \
  -H "Content-Type: application/json" \
  -d '{"event":"proxy_changed","profile_id":"demo-profile","proxy_id":"demo-proxy"}'
```

Refresh proxy state after a webhook:

```bash
curl -X POST http://localhost:8000/mlx/webhooks/refresh-proxy-state \
  -H "Content-Type: application/json" \
  -H "X-MLX-Token: <token>" \
  -d '{"profile_id":"demo-profile","extra":{}}'
```
