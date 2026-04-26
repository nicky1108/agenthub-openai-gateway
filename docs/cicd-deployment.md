# CI/CD Deployment To Your Server

This project now deploys as one server-side AgentHub gateway:

- FastAPI backend on `127.0.0.1:8787`
- built React frontend served by Nginx
- Nginx proxies `/v1/*`, `/auth/*`, `/portal/*` APIs, and `/admin/*` APIs to the backend
- `/`, `/product`, `/docs`, `/portal`, and `/admin` are SPA routes served from `frontend/dist`
- Codex CLI and Gemini CLI are installed directly on the server

## Recommended Production Layout

```text
/opt/agenthub-openai-gateway/
  current -> /opt/agenthub-openai-gateway/releases/<git-sha>
  releases/
    <git-sha>/
/etc/agenthub-openai-gateway.env
/etc/systemd/system/agenthub-openai-gateway.service
/etc/nginx/sites-available/agenthub-openai-gateway
```

## One-Time Server Setup

Assume Ubuntu and a deploy user named `agenthub`.

```bash
sudo useradd --system --create-home --shell /bin/bash agenthub
sudo mkdir -p /opt/agenthub-openai-gateway/releases
sudo chown -R agenthub:agenthub /opt/agenthub-openai-gateway

sudo apt-get update
sudo apt-get install -y nginx rsync git python3.11 python3.11-venv nodejs npm
```

Install local model runtimes:

```bash
npm install -g @openai/codex
npm install -g @google/gemini-cli
```

Copy runtime config:

```bash
sudo install -m 0644 deploy/systemd/agenthub-openai-gateway.service /etc/systemd/system/agenthub-openai-gateway.service
sudo install -m 0644 deploy/nginx/agenthub-openai-gateway.conf /etc/nginx/sites-available/agenthub-openai-gateway
sudo ln -sfn /etc/nginx/sites-available/agenthub-openai-gateway /etc/nginx/sites-enabled/agenthub-openai-gateway
```

Create `/etc/agenthub-openai-gateway.env`:

```env
APP_ENVIRONMENT=production
ADMIN_SECRET=replace-with-a-long-random-secret
SECRET_ENCRYPTION_KEY=replace-with-a-different-32-plus-character-secret
PUBLIC_GATEWAY_SERVICE_TOKEN=replace-with-a-long-random-service-token
DATABASE_URL=sqlite+aiosqlite:///./data/gateway.db
OPENAI_GATEWAY_HOST=127.0.0.1
OPENAI_GATEWAY_PORT=8787
FRONTEND_BASE_URL=https://your-domain.example
CODEX_NATIVE_ENABLED=true
GEMINI_NATIVE_ENABLED=true
PROVIDER_URL_STRICT_DNS=true
```

Leave `ADMIN_CLI_PROVIDER_MANAGEMENT_ENABLED` unset in production unless operators must create or edit CLI-backed providers through the admin API. If it is enabled, also set `ADMIN_CLI_PROVIDER_COMMAND_ALLOWLIST_CSV` to exact command names or paths, for example `codex,gemini`.

Enable services:

```bash
sudo systemctl daemon-reload
sudo systemctl enable agenthub-openai-gateway
sudo nginx -t
sudo systemctl reload nginx
```

## GitHub Secrets

Add these repository secrets:

```text
DEPLOY_HOST=<server-ip-or-domain>
DEPLOY_USER=agenthub
DEPLOY_SSH_KEY=<private-key-that-can-ssh-to-server>
DEPLOY_HEALTH_URL=https://your-domain.example/healthz
```

`DEPLOY_HEALTH_URL` is optional. If omitted, the workflow uses `http://DEPLOY_HOST/healthz`.

The deploy user must be able to run these commands without a password:

```text
sudo systemctl restart agenthub-openai-gateway
sudo nginx -t
sudo systemctl reload nginx
```

Recommended sudoers entry:

```text
agenthub ALL=(root) NOPASSWD: /bin/systemctl restart agenthub-openai-gateway, /usr/sbin/nginx -t, /bin/systemctl reload nginx
```

Paths may differ by distribution. Check with `which systemctl` and `which nginx`.

## Deployment Flow

On push to `main`, `.github/workflows/deploy.yml` will:

1. run backend tests
2. run frontend tests and build
3. rsync the repository to `/opt/agenthub-openai-gateway/releases/<git-sha>`
4. run `deploy/scripts/deploy.sh` on the server
5. switch `/opt/agenthub-openai-gateway/current`
6. restart the backend systemd service
7. reload Nginx
8. call `/healthz`

## Routes After Deployment

```text
https://your-domain.example/          public website
https://your-domain.example/product   product page
https://your-domain.example/docs      API docs
https://your-domain.example/portal    customer portal
https://your-domain.example/admin     operator admin console
https://your-domain.example/v1        OpenAI-compatible API base
```
