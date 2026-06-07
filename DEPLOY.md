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

## 4. HTTPS (do this before launch)

The compose file serves plain HTTP on :80. Two easy ways to add TLS:

- **Cloudflare (simplest):** put the domain behind Cloudflare and set SSL mode to
  "Flexible" (or "Full" with an origin cert). Zero server changes.
- **Caddy reverse proxy (auto Let's Encrypt):** run Caddy on :443 in front of the
  `web` container with a one-line `Caddyfile`:
  ```
  invoiceparsed.com {
      reverse_proxy web:80
  }
  ```
  Then change the `web` service to `expose: ["80"]` (drop the public `ports`) and
  publish `443:443` from Caddy.

## 5. Google OAuth (if enabled)

Because the app is now same-origin, update your Google Cloud OAuth client:

- **Authorized JavaScript origins:** `https://invoiceparsed.com`
- **Authorized redirect URIs:** `https://invoiceparsed.com/api/auth/google/callback`

(Plus `http://localhost:5173` / `http://localhost:5000/...` for local dev.)

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
