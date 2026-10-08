# InvoiceParsed

AI-powered invoice data extraction for small businesses & freelancers. Upload a
PDF or image, get clean structured data (vendor, line items, taxes, totals) as
JSON or CSV — in seconds.

This is a **full MVP** with the PRD's stack: a **Flask REST API** (Python) and a
separate **React + Vite** single-page frontend that talks to it over HTTP/JSON.

```
invoiceAI/
├── backend/     # Flask REST API  (Python)  → http://localhost:5000
└── frontend/    # React + Vite UI (the app) → http://localhost:5173
```

The two run as **separate servers**. The frontend calls the backend's `/api/*`
endpoints with your JWT; the backend does auth, usage limits, the OpenAI call,
and storage.

---

## Prerequisites

- Python 3.10+
- Node.js 18+

---

## 1. Backend (Flask API)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # then edit .env (see below)
python app.py                        # serves on http://localhost:5000
```

Edit `backend/.env`:

```env
OPENAI_API_KEY=sk-...                # ← your OpenAI key (required for extraction)
OPENAI_MODEL=gpt-4o                  # any vision-capable model
JWT_SECRET=<long-random-string>      # python -c "import secrets;print(secrets.token_urlsafe(48))"
DATABASE_URL=postgresql://invoiceparsed:invoiceparsed@db:5432/invoiceparsed  # see below
FRONTEND_ORIGIN=http://localhost:5173
APP_URL=http://localhost:5173        # used to build links in emails
GOOGLE_CLIENT_ID=                    # optional — enables Google sign-in
RESEND_API_KEY=                      # optional — enables password-reset emails
RESEND_FROM=InvoiceParsed <onboarding@resend.dev>
```

### The database when running on your machine

The app's database is Postgres, running as the `db` service in
`docker-compose.yml` (see [DB.md](DB.md)) — that's what the `DATABASE_URL` above
points at, and in Docker `docker-compose.yml` sets it for the container anyway.

`db` is a container hostname, though, so a Flask process running **directly on
your machine** can't resolve it. Two ways to run the API locally:

```bash
# A) Use the containerised Postgres over a published port (real parity)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db
# then in backend/.env:
#   DATABASE_URL=postgresql://invoiceparsed:invoiceparsed@localhost:5432/invoiceparsed

# B) Or skip Postgres entirely — SQLite needs no setup
#   DATABASE_URL=sqlite:///invoiceparsed.db
```

Either way the tables are created automatically on first run. Note that
`create_all()` adds missing *tables* but never alters existing ones, so a schema
change to a table you already have needs a manual `ALTER TABLE` (or, in dev on
SQLite, just delete `backend/invoiceparsed.db` and let it be recreated).

> The test suite doesn't care which of these you pick: it builds its own app on a
> temporary SQLite file, and `pytest` never touches your `DATABASE_URL`.

## 2. Frontend (React + Vite)

In a **second terminal**:

```bash
cd frontend
npm install
npm run dev                          # serves on http://localhost:5173
```

`frontend/.env` points the UI at the API and (optionally) enables Google:

```env
VITE_API_URL=http://localhost:5000
VITE_GOOGLE_CLIENT_ID=               # same value as backend GOOGLE_CLIENT_ID
```

Open **http://localhost:5173** and sign up.

## Enabling Google sign-in & password-reset emails

- **Google:** create an OAuth 2.0 **Web application** client in the
  [Google Cloud Console](https://console.cloud.google.com/apis/credentials).
  Add `http://localhost:5173` to *Authorized JavaScript origins*. Put the client
  ID in **both** `backend/.env` (`GOOGLE_CLIENT_ID`) and `frontend/.env`
  (`VITE_GOOGLE_CLIENT_ID`). The "Continue with Google" button appears
  automatically once set. Leave blank to hide it.
- **Email (Resend):** create an API key at [resend.com](https://resend.com) and
  set `RESEND_API_KEY`. For testing you can send from `onboarding@resend.dev`;
  for production verify your domain and set `RESEND_FROM` to an address on it.
  Without a key, "forgot password" still succeeds silently (the email is skipped
  and logged) so local dev isn't blocked.

---

## Turning on analytics

Nothing is tracked until you set a key, and with none set the build ships no
third-party requests. Pick either provider (or both) in `frontend/.env`:

```env
VITE_PLAUSIBLE_DOMAIN=invoiceparsed.com   # your site as registered at plausible.io
VITE_POSTHOG_KEY=                         # optional, instead of or alongside
VITE_ANALYTICS_DEBUG=false                # true → log events to the console, send nothing
```

> **Vite bakes `VITE_*` at build time.** In the Docker deploy these are build
> args, so put them in the **root** `.env` and `docker compose up -d --build` —
> a plain restart won't pick them up.

The funnel is already instrumented end to end, so the questions you actually
need answered are answerable on day one:

| Step | Event |
| ---- | ----- |
| Landed | `pageview` (one per SPA route change) |
| Tried the extractor without an account | `demo_started` → `demo_completed` |
| Hit the export gate on a demo result | `demo_export_blocked` |
| Created an account | `signup_submitted` → `signup_verified` |
| Kept the demo result | `demo_claimed` |
| Used the product | `extract_started` → `extract_completed` |
| Started paying | `checkout_started` → `payment_succeeded` |

## The try-before-signup demo

The landing page lets a stranger extract one real document with **no account** —
the biggest single lever on signup conversion, since the old flow demanded an
email and a confirmed inbox before showing anything.

How it's kept from being abused or expensive:

- **One per visitor, server-side.** `DEMO_FREE_EXTRACTIONS` (default 1) is capped
  per IP in the `demo_usage` table, keyed by a *salted hash* of the address — the
  IP itself is never stored. The counter is durable: restarting the app or purging
  old results does not hand anyone a fresh freebie.
- **The attempt is counted before the model call**, so a failed-but-paid-for
  extraction can't be retried in a loop.
- **One file, invoices and receipts only.** Bank statements are the costliest and
  slowest document type, so they stay behind a paid plan. Batch and multi-page
  stay paid capabilities too.
- **A burst limit** (`RATELIMIT_DEMO`, default `6 per hour`) sits on top of the cap.
- **Nothing lands in anyone's account.** A demo creates no `Extraction` row, so no
  quota is spent and nothing can leak into a stranger's history.
- **Results expire.** Unclaimed results and their uploaded files are purged after
  `DEMO_RETENTION_HOURS` (default 24), opportunistically on demo requests — no
  scheduler to run.

Set `DEMO_ENABLED=false` to remove the widget entirely. It also hides itself when
`OPENAI_API_KEY` is unset, and for visitors who are already signed in.

**Claiming.** A finished demo returns a single-use `claimToken`, which the browser
keeps in `localStorage`. On the next successful sign-in — by any route: email,
Google, or the verification link — the app posts it to `/api/demo/claim`, which
turns it into a real `Extraction` owned by that user and moves the stored original
across so the document viewer works on it. The claim counts toward their monthly
usage like any other extraction. A stale, unknown or already-used token reports
nothing-to-claim rather than erroring, because the browser retries on every
sign-in while it holds one.

> **Deployment note:** the per-IP cap is only as good as `request.remote_addr`, so
> `PROXY_HOPS` must match your setup (`1` behind nginx, `2` behind Caddy → nginx,
> `0` running Flask directly). Get this wrong behind a proxy and every visitor
> looks like the same IP — the first person to try the demo would use everyone's
> free extraction.

## Where do I put my OpenAI API key?

In **`backend/.env`**, as `OPENAI_API_KEY`. The key lives only on the server and
is read by [backend/openai_service.py](backend/openai_service.py) — it is never
sent to the browser. Restart `python app.py` after changing it.

---

## How it fits together

```
Browser (React SPA :5173)
   │  fetch /api/... with  Authorization: Bearer <JWT>
   ▼
Flask API (:5000)
   ├── /api/auth/*        register / login / me   (JWT + werkzeug password hash)
   ├── /api/demo/*        try-before-signup: anonymous extract + claim (no auth)
   ├── /api/extract       upload → OpenAI vision → structured JSON  (enforces plan limit)
   ├── /api/extractions   list / get / delete / CSV download
   ├── /api/usage         monthly usage vs plan limit
   └── /api/billing/upgrade   change plan (Paystack; demo stub when unconfigured)
        │
        ├── Postgres (users, extractions)  via SQLAlchemy — bundled `db` service
        └── OpenAI API                    via the openai SDK
```

The frontend stores the JWT in `localStorage` and attaches it to every request
(see [frontend/src/lib/api.js](frontend/src/lib/api.js)). Auth state lives in a
React context ([frontend/src/lib/auth.jsx](frontend/src/lib/auth.jsx)).

---

## API reference

| Method | Endpoint                     | Auth | Description                       |
| ------ | ---------------------------- | ---- | --------------------------------- |
| POST   | `/api/auth/register`         | —    | Create account → `{user, needsVerification}` (no token until email confirmed) |
| POST   | `/api/auth/login`            | —    | Login → `{user, token}` (403 `email_unverified` if not confirmed) |
| POST   | `/api/auth/verify-email`     | —    | Confirm email from link → `{user, token}` |
| POST   | `/api/auth/resend-verification` | — | Re-send the confirmation email    |
| POST   | `/api/auth/google`           | —    | Google sign-in (ID token) → `{user, token}` |
| POST   | `/api/auth/google/callback`  | —    | Google redirect-mode landing (form POST) |
| POST   | `/api/auth/forgot-password`  | —    | Email a reset link (via Resend)   |
| POST   | `/api/auth/reset-password`   | —    | Set a new password from a token   |
| GET    | `/api/auth/me`               | ✓    | Current user + usage              |
| GET    | `/api/demo/status`           | —    | Free demo extractions left for this IP |
| POST   | `/api/demo/extract`          | —    | **No account.** One file → structured JSON + claim token |
| POST   | `/api/demo/claim`            | ✓    | Adopt a demo extraction into the signed-in account |
| POST   | `/api/extract`               | ✓    | multipart `file` → structured JSON |
| GET    | `/api/extractions`           | ✓    | List extractions                  |
| GET    | `/api/extractions/<id>`      | ✓/🔑 | Single extraction                 |
| PATCH  | `/api/extractions/<id>`      | ✓/🔑 | Persist edited invoice fields     |
| DELETE | `/api/extractions/<id>`      | ✓/🔑 | Delete extraction                 |
| GET    | `/api/extractions/<id>/csv`  | ✓/🔑 | Download CSV                      |
| GET    | `/api/extractions/<id>/files`| ✓/🔑 | List stored original files        |
| GET    | `/api/extractions/<id>/file/<n>` | ✓/🔑 | Fetch an original page/file   |
| GET    | `/api/usage`                 | ✓    | Usage vs plan limit               |
| GET    | `/api/billing/config`        | —    | Whether billing is live or demo   |
| POST   | `/api/billing/checkout`      | ✓    | Start Paystack checkout → `{url}` (or demo switch) |
| POST   | `/api/billing/upgrade`       | ✓    | Instant plan switch (demo)        |
| POST   | `/api/billing/verify`        | ✓    | Verify a Paystack `reference` after checkout |
| POST   | `/api/billing/webhook`       | 🔒   | Paystack webhook (HMAC-SHA512 signed) |
| GET/POST/DELETE | `/api/keys[/<id>]`  | ✓    | Manage API keys (Pro)             |
| GET/POST/DELETE | `/api/webhooks[/<id>]` | ✓ | Manage webhooks (Pro)            |
| POST   | `/api/webhooks/<id>/test`    | ✓    | Send a test webhook               |
| GET    | `/api/health`                | —    | Health + whether OpenAI is set    |
| GET    | `/api/plans`                 | —    | Plan catalog                      |

`✓` = JWT session · `🔑` = JWT **or** a Pro API key (`Authorization: Bearer ip_live_…`
or `X-API-Key`) · `🔒` = no auth header, verified by request signature.
Extraction/read endpoints accept both; account, billing, key and webhook
management are JWT-only. Extraction events are POSTed to active webhooks, signed
with `X-InvoiceParsed-Signature: sha256=<HMAC>`, and **retried with exponential
backoff** until a 2xx (see `WEBHOOK_*` settings).

The webhook body is `{ "event": "extraction.completed", "data": { … } }`, where
`data` is the extraction payload — including **`docType`** (`"invoice"` or
`"receipt"`) and the parsed document under `invoice`:

```json
{
  "event": "extraction.completed",
  "data": {
    "id": "…",
    "docType": "receipt",
    "fileName": "lunch.jpg",
    "status": "completed",
    "createdAt": "2026-06-09T…Z",
    "invoice": { "merchant": { "name": "Cafe Roma" }, "total": 10.30, "…": "…" },
    "files": [ … ]
  }
}
```

All endpoints are **rate-limited** per IP (`RATELIMIT_DEFAULT`); credential and
email-sending auth endpoints get a tighter budget (`RATELIMIT_AUTH`). Over the
limit returns `429` with `{"code": "RATE_LIMITED"}`.

The `/api/extract` payload follows the PRD invoice schema — see
[backend/invoice_schema.py](backend/invoice_schema.py).

---

## Features

- **Landing page** — animated hero (invoice → JSON), features, how-it-works,
  API teaser, pricing.
- **Try before signup** — the landing page runs a **real extraction with no
  account**: one free document per visitor (per-IP, server-enforced). The parsed
  fields are shown in full; exporting is what asks for the account. The result is
  held server-side under a single-use claim token, so signing up **adopts that
  extraction** instead of making them upload it again. Off via `DEMO_ENABLED=false`.
- **Funnel analytics** — optional Plausible and/or PostHog, configured purely by
  env (`VITE_PLAUSIBLE_DOMAIN`, `VITE_POSTHOG_KEY`). With neither set, no
  third-party script is loaded at all. Tracks pageviews plus the funnel that
  matters: demo started/completed → signup → extract → checkout → payment. Event
  names live in `frontend/src/lib/analytics.js`.
- **Auth** — email/password signup & login, **Google sign-in/sign-up** (Google
  Identity Services → backend ID-token verification), **forgot/reset password**
  via emailed single-use links, JWT sessions, protected routes.
- **Extract** — drag & drop / picker (PDF, JPG, PNG ≤ 10MB), live processing
  states, structured result card, JSON copy/download, CSV export.
- **Inline editing (saved)** — correct any field in the result card and **Save**;
  edits persist via `PATCH /api/extractions/<id>` and update the stored record.
- **Original document viewer** — uploaded files are stored and rendered back in
  the card / detail page (images + PDFs, with a page switcher for multi-page).
- **REST API** *(Pro)* — create API keys in the dashboard and hit the same
  endpoints programmatically with `X-API-Key` / `Authorization: Bearer ip_live_…`.
- **Webhooks** *(Pro)* — register endpoints that receive a signed
  `extraction.completed` POST whenever an extraction finishes; failed deliveries
  are retried with exponential backoff; test deliveries from the dashboard.
- **Per-field confidence scores** — every extraction returns a 0–100% confidence
  per field (model self-assessed); shown as colour-coded badges in the result
  card plus an overall "% confident" pill.
- **Multi-file batch upload** *(paid)* — select many invoices at once; each is
  extracted into its own record, processed sequentially with live per-file
  status. Stops gracefully if the monthly limit is hit.
- **Multi-page invoices** *(paid)* — select several pages/files and "Combine
  into one invoice"; all pages go to the model in a single call and merge into
  one record. Multi-page PDFs work on any plan (one file).
- **Usage & limits** — monthly tracking; free tier capped at 5/month with
  upgrade prompts. `batch` and `multiPage` are plan capabilities gated
  server-side (Starter + Pro), exposed via `usage.capabilities`.
- **History** — searchable table with view / CSV / delete.
- **Billing** — Free / Starter / Pro / **Business** plans. Live **Paystack**
  hosted checkout when configured (plan applied on the verified callback and by
  the signed webhook), with an instant-switch demo mode when no key is set.
- **Abuse protection** — per-IP rate limiting on all endpoints, with a tighter
  budget on auth/credential routes (Flask-Limiter; Redis-backed in prod).
- **B2C + B2B positioning** — the landing page has a "who it's for" split
  (individuals vs teams) and an **Individuals / Businesses** pricing toggle that
  swaps the plan set; plans carry a `segment` tag (`personal` / `business` /
  `both`). Accounts remain single-user.
- **Upload progress** — a real byte-percentage bar during upload (per-file in
  batch mode), then an indeterminate "reading → structuring" indicator while the
  model runs.

---

## Tests

```bash
cd backend
pytest                 # runs the suite in backend/tests
```

The suite covers auth + email verification, plan-capability gating (batch /
multi-page / usage limits), the try-before-signup demo (per-IP cap, claiming,
retention purge), webhook signing & retry/backoff, and billing
(demo upgrade, Paystack checkout, signed webhooks). Tests use a temporary SQLite DB
and stub all external services — nothing leaves the machine.

## Going to production

- **Secrets:** set a strong `JWT_SECRET` in `backend/.env`.
- **Database:** nothing to provision — Postgres runs as the `db` service in
  `docker-compose.yml`, with a nightly backup into `./backups`. Copy the root env
  template (`cp .env.example .env`) and set `POSTGRES_PASSWORD` before deploying.
  It isn't published to the host, so only the other containers can reach it. See
  [DB.md](DB.md) for backups, restores, inspecting it, and migrating in from a
  managed Postgres. `create_all()` creates missing tables but won't alter
  existing ones, so new *columns* need a manual `ALTER TABLE`.
- **WSGI server:** serve Flask with gunicorn (config included):
  ```bash
  cd backend
  gunicorn -c gunicorn.conf.py wsgi:app
  ```
  Serve the frontend as a static build (`npm run build` → deploy `frontend/dist`).
- **Payments (Paystack):** set `PAYSTACK_SECRET_KEY` — that's it. The recurring
  monthly plans are provisioned in Paystack automatically from `plans.py` the first
  time each tier is bought (`PAYSTACK_PLAN_*` exist only to pin a tier to a
  hand-made plan). The billing UI opens a hosted Paystack checkout via
  `POST /api/billing/checkout`. The plan is applied twice over, idempotently:
  `POST /api/billing/verify` confirms the transaction reference the browser
  returns with, and `POST /api/billing/webhook` (HMAC-SHA512 signature-verified
  with the same secret key) handles the async confirmation and renewals. With no
  key set, billing runs in demo mode (instant switch).
- **Rate limiting:** enabled by default (per-IP). In production set
  `RATELIMIT_STORAGE_URI=redis://...` so limits are shared across workers.
- **Demo tables:** the try-before-signup feature adds two *new* tables
  (`demo_usage`, `demo_extractions`). `create_all()` creates missing tables on
  boot, so this one needs **no migration** — unlike a new column on an existing
  table. Confirm `PROXY_HOPS` is right for your proxy chain, or the per-IP cap
  will treat every visitor as one person.
- **CORS:** set `FRONTEND_ORIGIN` (comma-separated) to your deployed frontend
  URL(s).
