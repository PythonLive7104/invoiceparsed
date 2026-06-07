# Deploying InvoiceParsed (Docker, single VPS)

This deploys two containers — the Flask API (gunicorn) and an nginx that serves
the React SPA and reverse-proxies `/api` to the API. The database (Supabase),
OpenAI and Resend are external, so nothing else runs on the box.

Tested target: a 2 GB / 1 vCPU / 40 GB KVM VPS (e.g. InterServer $3/mo).

---

## 0. Provision the VPS

- **Use Ubuntu *Server* 24.04**, not Desktop — a desktop GUI wastes ~0.5–1 GB of
  your 2 GB on something a server never uses.
- Point your domain's DNS **A record** at the VPS IP (e.g. `invoiceparsed.com`).

## 1. First-time server setup

SSH in as root (or a sudo user), then:

```bash
# Update
apt update && apt -y upgrade

# 2 GB swap — safety net for image builds / memory spikes on a 2 GB box
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# Docker + compose plugin
curl -fsSL https://get.docker.com | sh

# Run docker without sudo (fixes "permission denied … docker.sock").
# Log out/in after this for the group to take effect.
usermod -aG docker $USER
```

## 2. Get the code and configure secrets

```bash
git clone <your-repo-url> invoiceparsed && cd invoiceparsed
cp backend/.env.example backend/.env
nano backend/.env
```

Set these for production in `backend/.env`:

| Key | Value |
|-----|-------|
| `JWT_SECRET` | a long random string — `python3 -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `SUPABASE_URL` | your Supabase pooler connection string |
| `OPENAI_API_KEY` | your OpenAI key |
| `RESEND_API_KEY`, `RESEND_FROM` | Resend key + verified sender |
| `APP_URL` | `https://invoiceparsed.com` (used in email links) |
| `FRONTEND_ORIGIN` | `https://invoiceparsed.com` (CORS allow-list) |
| `GOOGLE_CLIENT_ID` | your Google OAuth client id (optional) |
| `DODO_*` | leave blank until you have a Dodo account (billing runs in demo mode) |

> The frontend is built **same-origin** (`VITE_API_URL=""`), so the browser calls
> `/api` on your domain and nginx proxies it to the API — no separate API
> subdomain or CORS round-trips needed.

## 3. Build and run

```bash
docker compose up -d --build
```

That's it — the app is live on **port 80**. Check it:

```bash
docker compose ps
curl -s localhost/api/health        # {"status":"ok",...}
docker compose logs -f backend      # tail logs
```

Updating later:

```bash
git pull && docker compose up -d --build
```

## 4. HTTPS / SSL certificate

The base compose serves plain HTTP on :80. To get a real, auto-renewing SSL
certificate, use the included **Caddy** override — it obtains and renews a free
Let's Encrypt certificate automatically and proxies to the app over HTTPS.

**Prerequisites:** your domain's DNS **A record** (and `www`, if used) must point
at this server's IP, and ports **80 + 443** must be open. Let's Encrypt cannot
issue a certificate for a bare IP — you need the domain pointed first.

```bash
# Replace with your domain. Brings up backend + web + caddy (TLS).
SITE_DOMAIN=invoiceparsed.com \
  docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Caddy fetches the certificate on first start (watch `docker compose logs caddy`).
Then `https://invoiceparsed.com` works, with HTTP auto-redirecting to HTTPS and
`www` redirecting to the apex. Certificates are stored in the `caddy_data`
volume and renew automatically — don't delete that volume.

> Tip: persist these in a root `.env` (Compose reads it automatically), then just
> run `docker compose up -d --build`:
> ```
> COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml
> SITE_DOMAIN=invoiceparsed.com
> # Build-time frontend vars (Vite bakes them in; frontend/.env is NOT used by Docker):
> VITE_GOOGLE_CLIENT_ID=xxxxx.apps.googleusercontent.com   # required for the Google button to show
> VITE_SENTRY_DSN=                                          # optional (frontend error monitoring)
> ```
> ⚠️ After changing any `VITE_*` value you must **rebuild** (`--build`) — they're
> compiled into the static bundle, not read at runtime.

**Alternative (no server TLS): Cloudflare.** Put the domain behind Cloudflare and
set SSL mode to Full — TLS terminates at Cloudflare with zero server changes.
Keep the base compose (port 80) for the origin.

## 5. Google OAuth (if enabled)

Because the app is now same-origin, update your Google Cloud OAuth client:

- **Authorized JavaScript origins:** `https://invoiceparsed.com`
- **Authorized redirect URIs:** `https://invoiceparsed.com/api/auth/google/callback`

(Plus `http://localhost:5173` / `http://localhost:5000/...` for local dev.)

## 6b. Error monitoring (Sentry) — optional

Create a project at sentry.io (one "Python/Flask" + one "React"), then:

- `backend/.env`: set `SENTRY_DSN=` to the backend DSN.
- Root compose `.env`: set `VITE_SENTRY_DSN=` to the frontend DSN, then rebuild
  (`docker compose up -d --build`).

Both stay disabled when their DSN is blank, so dev/tests never report.

## 6. Dodo Payments (when ready)

Add `DODO_API_KEY`, `DODO_WEBHOOK_SECRET` and the `DODO_PRODUCT_*` ids to
`backend/.env`, then `docker compose up -d`. Point the Dodo webhook at
`https://invoiceparsed.com/api/billing/webhook`. Until then, billing stays in
instant-switch demo mode.

---

## Notes / sizing

- **Memory budget:** nginx (~30 MB) + gunicorn (2–3 gthread workers, ~400–700 MB)
  fits well under 2 GB. Scale workers with `WEB_CONCURRENCY` in `backend/.env`.
- **Persistence:** uploaded originals are kept in the `uploads` Docker volume.
- **Rate limiting** uses in-process memory (fine for one box). If you later run
  multiple API replicas, set `RATELIMIT_STORAGE_URI=redis://…` and add a Redis
  service.
- **Building on a 2 GB box:** the Vite build is memory-light, and the swap from
  step 1 covers any spike. Alternatively build images elsewhere and push to a
  registry.
