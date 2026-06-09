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
DATABASE_URL=sqlite:///invoiceparsed.db  # SQLite for dev; swap to Postgres for prod
FRONTEND_ORIGIN=http://localhost:5173
APP_URL=http://localhost:5173        # used to build links in emails
GOOGLE_CLIENT_ID=                    # optional — enables Google sign-in
RESEND_API_KEY=                      # optional — enables password-reset emails
RESEND_FROM=InvoiceParsed <onboarding@resend.dev>
```

The SQLite database and tables are created automatically on first run.

> **Upgrading an existing dev DB:** the auth additions changed the `users`
> table (nullable password, `google_sub`, `image`). SQLite won't auto-migrate —
> delete `backend/invoiceparsed.db` once so it's recreated with the new schema.

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
   ├── /api/extract       upload → OpenAI vision → structured JSON  (enforces plan limit)
   ├── /api/extractions   list / get / delete / CSV download
   ├── /api/usage         monthly usage vs plan limit
   └── /api/billing/upgrade   change plan (Dodo Payments stub)
        │
        ├── SQLite (users, extractions)   via SQLAlchemy
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
| POST   | `/api/billing/checkout`      | ✓    | Start Dodo checkout → `{url}` (or demo switch) |
| POST   | `/api/billing/upgrade`       | ✓    | Instant plan switch (demo)        |
| POST   | `/api/billing/webhook`       | 🔒   | Dodo webhook (Standard-Webhooks signed) |
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
- **Billing** — Free / Starter / Pro / **Business** plans. Live **Dodo Payments**
  hosted checkout when configured (plan applied via signed webhook), with an
  instant-switch demo mode when no API key is set.
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
multi-page / usage limits), webhook signing & retry/backoff, and billing
(demo upgrade, Dodo checkout, signed webhooks). Tests use a temporary SQLite DB
and stub all external services — nothing leaves the machine.

## Going to production

- **Secrets & DB:** set a strong `JWT_SECRET` and point the database at Postgres
  (this project ships with `psycopg2-binary`; Supabase's pooler works — see
  `SUPABASE_URL`). `create_all()` won't alter existing tables, so apply schema
  changes with a migration/SQL when upgrading.
- **WSGI server:** serve Flask with gunicorn (config included):
  ```bash
  cd backend
  gunicorn -c gunicorn.conf.py wsgi:app
  ```
  Serve the frontend as a static build (`npm run build` → deploy `frontend/dist`).
- **Payments (Dodo):** set `DODO_API_KEY`, `DODO_WEBHOOK_SECRET`, and the
  `DODO_PRODUCT_*` ids. The billing UI then opens a hosted Dodo checkout via
  `POST /api/billing/checkout`, and `POST /api/billing/webhook`
  (Standard-Webhooks signature-verified) applies the plan on payment. With no
  key set, billing runs in demo mode (instant switch).
- **Rate limiting:** enabled by default (per-IP). In production set
  `RATELIMIT_STORAGE_URI=redis://...` so limits are shared across workers.
- **CORS:** set `FRONTEND_ORIGIN` (comma-separated) to your deployed frontend
  URL(s).
