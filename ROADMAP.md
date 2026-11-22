# InvoiceParsed — Platform Roadmap

Target: evolve InvoiceParsed from an invoice extraction tool into an AI-powered
financial operations platform covering
**PO → Goods Received → Invoice → Extraction → Validation → Duplicate Detection
→ Three-Way Matching → Approval → Payment Tracking → Bank Reconciliation →
Analytics → AI Insights.**

This document is the execution plan. Steps are ordered by dependency, not by
appeal. Each step states what it unblocks and how we know it is done.

**Status key:** `[x]` done · `[~]` in progress · `[ ]` not started

---

## Phase 0 — Audit findings (complete)

The audit is done; the findings below drive the ordering of everything that
follows.

### What exists today

| Area | Implementation |
|---|---|
| Backend | Flask 3 REST API, blueprints under `backend/routes/`, app factory in `app.py` |
| Frontend | React 18 + Vite SPA, React Router, Tailwind, code-split routes, prerendered marketing pages |
| Database | Postgres in Docker (`db` service); SQLite fallback for host dev. SQLAlchemy ORM |
| Auth | JWT (30-day, HS256) in `localStorage`; Google Identity Services; API keys (`ip_live_`, SHA-256 hashed) |
| AI extraction | OpenAI vision via `chat.completions` with `response_format=json_schema` (strict). Three doc types: invoice, receipt, statement |
| Documents | Originals saved to disk per extraction (`uploads/<id>/<n>__<name>`) |
| Billing | Paystack (plans auto-provisioned). **Migrating to Bachs — see Open Decisions** |
| Plans | free / starter / pro / business, with server-side capability gating in `plans.py` |
| Admin | Flask-Admin at `/admin` behind HTTP Basic |
| Infra | docker-compose: Postgres, Redis (rate limits), backend, nginx+SPA, nightly `pg_dump`. Caddy for TLS |
| Monitoring | Sentry (backend + frontend), gated on DSN |
| Tests | 119 backend tests (pytest). No frontend tests, no CI |

### Strengths worth preserving

- Plan capabilities are gated **server-side**, not merely hidden in the UI.
- Soft-deleted extractions still count toward quota, so deleting history cannot
  reset a plan allowance.
- The anonymous demo's per-IP counter is a salted hash and survives result purges.
- Code comments explain *why*, which made this audit far faster than usual.

### Blocking structural gaps

These are the reasons the phase ordering below looks the way it does.

1. **No multi-tenancy at all.** The model is `User → Extraction`. There is no
   Organization, Membership, Role or Permission anywhere in the codebase. Every
   Phase 2–4 feature (suppliers, POs, approvals, analytics scoping, the AI
   assistant) is meaningless without a tenant boundary. **This gates Phases 2–4.**
2. **Money is `float`.** `Extraction.total` is `db.Column(db.Float)` and
   `invoice_schema._num()` returns `float`. Binary floating point cannot
   represent 0.10 exactly, so summing line items drifts from stated totals. That
   is unacceptable in a product making financial assertions, and it **gates all
   validation and matching work**, because tolerance checks over float totals
   manufacture false discrepancies.
3. **Extraction is synchronous.** The OpenAI call runs inside the HTTP request,
   holding a gunicorn thread (16 concurrent slots total: 4 workers x 4 threads,
   300s timeout). A `processing` row is created but nothing resumes it, so a
   worker restart leaves rows stuck in `processing` forever — invisible to the
   usage counter and unrecoverable by the user. **This gates reliability.**
4. **No migrations** — was `db.create_all()` only, which never adds a column to
   an existing table. **Fixed in F1 below.**
5. **Extraction field coverage is roughly 40% of the target schema.** Missing
   entirely: all customer/buyer fields, PO reference, invoice type, discount,
   tax percentage, shipping, other charges, amount paid, outstanding balance,
   supplier phone / tax ID / registration number / bank details, and per-line-item
   product name, discount and tax rate.
6. **No background queue, no audit log, no notifications, no RBAC.**

### Known defects found and already fixed

- `POST /api/billing/upgrade` granted any paid plan to any authenticated user
  with no payment, in production. Now refused when a provider is configured.
- `/api/extract` had no per-user ceiling (only 300/min per IP) and no page cap,
  so one scripted account on an unlimited plan could run up an unbounded OpenAI
  bill. Now capped per account, with a page limit.
- Webhook URLs were validated on scheme only — an SSRF vector reaching Postgres,
  Redis, the API itself and cloud instance metadata. Now DNS-resolved and
  rejected for private / loopback / link-local targets, and re-checked on every
  delivery attempt so DNS rebinding cannot slip past.

### Deferred items (tracked, not yet scheduled)

- JWTs cannot be revoked; a password change does not invalidate existing tokens.
- Uploaded originals are kept forever (unbounded disk growth, no retention policy).
- `/extractions` is capped at 300 rows with no pagination.
- 23 uses of deprecated `datetime.utcnow()`; 29 of legacy `Model.query.get()`.
- No React error boundary, though `@sentry/react` is installed.
- No CI and no linting.
- `frontend/.env` is committed to the repository.

---

## Foundation — must precede feature work

### [x] F1. Database migrations (Alembic)

Done. Flask-Migrate wired in; the baseline revision was generated and verified to
reproduce the models exactly (autogenerate reports no drift). `db_bootstrap.py`
handles three cases: an empty database, a pre-migration database (stamps the
baseline so the existing production database is adopted **without touching its
data** — verified against a seeded database), and a database already under
Alembic. `docker_entrypoint.py` runs it before gunicorn and refuses to start the
server if it fails. `AUTO_CREATE_TABLES=false` in the deploy.

*Unblocks:* every schema change below.

### [x] F2. Decimal money

Done. `money.py` is the single parser (`money`, `rate`, `money_sum`, `as_json`),
with ROUND_HALF_UP rather than Python's banker's rounding, and tolerant parsing
of what documents and hand edits actually contain — currency symbols, thousands
separators, European decimal commas, accounting parentheses for negatives.
`extractions.total` is `Numeric(18, 4)`; all three schema normalizers produce
Decimal (money at 2 places, quantities and unit prices at 4).

**API contract change:** money crosses the wire as an exact decimal string
(`"19.99"`), not a JSON number, because every JS client reads a JSON number back
as an IEEE-754 double. `json_provider.py` enforces this for Flask responses,
stored payloads and webhook bodies alike, so all three agree.
`Intl.NumberFormat.format()` accepts decimal strings directly (verified,
including a 16-digit amount a float would corrupt), so display needed no float.

`documents.load_document()` re-normalizes stored payloads on read. That keeps the
spreadsheet exporters emitting *numbers* rather than text — otherwise an Excel
export looks correct and `SUM()` over the column returns 0 — and converts
pre-Decimal rows on the way out instead of needing a data migration. It also
closed the unguarded `json.loads` 500s in the CSV and XLSX endpoints.

65 new tests (`test_money.py`, `test_decimal_pipeline.py`) covering the module
and every hop: extraction → storage → API → PATCH → CSV → XLSX → webhook.

*Still open:* an explicit currency code is stored per extraction but nothing yet
prevents summing across currencies — that belongs with the analytics work (P4.1).

*Acceptance met:* a line-item set sums to its stated total exactly, with no
epsilon tolerance.

### [x] F3. Multi-tenancy (Organization + RBAC)

Done. `Organization` and `OrganizationMembership` exist; `organization_id` is on
`extractions`, `api_keys`, `webhooks`, `payments` and `subscriptions`. Tenant
scoping lives in `tenancy.scoped()`, which **raises rather than returning an
unfiltered query** when no organization is attached — a forgotten filter can no
longer silently become "every tenant's rows".

**The plan moved from `users.plan` to `organizations.plan`.** A team shares one
monthly allowance; a per-user plan would hand every colleague their own quota,
and "number of users" could not be a pricing dimension at all. Usage counting is
per organization too.

Eight roles with permissions defined as data in `roles.py` (owner,
administrator, finance manager, accountant, procurement officer, department
manager, approver, viewer), including permissions for Phase 2 features that do
not exist yet, so role definitions stay stable as those land.
`suppliers:bank:read` is deliberately separate — bank details are the
highest-value target in the dataset.

Request resolution: an `X-Organization-Id` header validated against membership
(a non-member gets **403, not a silent fall back** — falling back would make
probing someone else's id look successful), else an API key's own organization,
else the caller's personal organization. An API key cannot be redirected to
another organization by that header.

Existing accounts keep working untouched: the migration gives each user a
personal organization, carrying over their old plan, and attributes all their
rows to it. Verified against a seeded pre-tenancy database — paid plans
preserved, nothing left unattributed.

*Acceptance met:* 22 cross-tenant tests covering reads, edits, deletes, exports,
file downloads, list endpoints, usage counting, API-key scope, role refusals and
webhook dispatch.

### [ ] F4. Background job queue

Move extraction off the request path. RQ on the existing Redis is the smallest
step; Celery if we also want scheduled jobs. Return `202` with a job id and poll
`/extractions/<id>`. Needs a retry policy with backoff, idempotency keys,
per-job timeouts, a sweeper that fails rows stuck in `processing`, and separate
queues so a 60-page bank statement cannot starve single-invoice uploads.

*Acceptance:* `processing` is always truthful — no row stays in it after a worker
restart, and a failed job never consumes plan quota.

### [~] F5. CI, linting, and a test baseline

Done: `.github/workflows/ci.yml` runs on every push and PR —

- **Backend**: ruff lint, the full pytest suite, and a **migration drift check**
  that applies every migration to an empty database and then asserts
  autogenerate finds nothing left to do. That catches the common failure of
  editing a model and forgetting to generate a revision. Verified in both
  directions: it passes on a clean tree and fails when a column is added without
  a migration.
- **Frontend**: `npm run build`, which covers the sitemap, Vite build and
  prerender, so a broken import or missing export fails the job.
- Provider credentials are pinned blank in the job env so a runner variable can
  never point the suite at a real OpenAI, Resend or Bachs account.

`backend/ruff.toml` selects pyflakes, pycodestyle, import sorting, bugbear,
pyupgrade, comprehensions, returns and simplify. The baseline is clean.

**Frontend install fixed.** `@vitejs/plugin-react` upgraded 4.x → 6.3.0, which
supports vite 8 (its three extra peers are all optional). The lockfile was
regenerated. A plain `npm ci` now succeeds, where before it failed with ERESOLVE
on a fresh clone — so `--legacy-peer-deps` is gone from both `frontend/Dockerfile`
and CI. Verified by a clean `rm -rf node_modules && npm ci && npm run build`,
including the prerender pass that executes the app across 24 routes.

**Vitest added** with `frontend/vitest.config.js` and 10 tests pinning the money
contract — `formatMoney` on exact decimal strings (including a value past 2^53
where the float form is demonstrably wrong) and `numericInput` never converting
user input to a float. `npm test` is wired into CI.

*Caveat:* the suite cannot be run from `c:\Users\DELL\Documents\invoiceparsed\frontend`
on this machine. Vitest fails there at `import { … } from "vitest"` with
"Cannot read properties of undefined (reading 'config')". It is environmental,
not a code or dependency problem: the identical tree — same `package.json`,
same lockfile, same configs — passes when copied to another directory. Ruled
out: vite/vitest versions, duplicate installs, the config files, ESM mode,
worker pool, caches, file location and OneDrive. Likely a filesystem or
security-software interaction with that path. CI runs on Linux and is
unaffected.

**Also still to do:** eslint (not yet configured).

---

## Phase 1 — Make the existing product reliable (highest priority)

### [x] P1.1 Extraction accuracy and coverage

Done. The invoice schema went from 10 top-level fields to 19, and the prompt was
rewritten to describe all of them.

**New:** `customer` (name, address, email, phone, tax ID), vendor phone / tax ID
/ registration number / **bank details** (bank, account name and number, IBAN,
SWIFT, sort code), `invoice_type` (invoice / credit_note / debit_note /
proforma / receipt), `purchase_order_reference`, `discount`, `tax_percentage`,
`shipping`, `other_charges`, `amount_paid`, `balance_due`, and per-line
`product_name`, `discount` and `tax_rate`.

Why these in particular: vendor bank details are what invoice-redirection fraud
alters, so they are captured and shown read-only for verification;
`invoice_type` stops a credit note being counted as a charge; and
`purchase_order_reference` is the key P2.3 matching will join on.

The prompt now also states who is vendor vs customer explicitly, warns about
regional date ambiguity (03/04 differs by country), handles parenthesised
negatives, and tells the model to leave `amount_paid` / `balance_due` null
rather than computing them - the application does that deterministically.

Confidence stays a parallel object rather than per-field `{value, confidence}`
wrappers: OpenAI strict mode requires every property in `required`, so wrapping
would double the schema and force a score for fields never seen. There is a test
asserting the schema stays strict-mode valid, since a violation is rejected at
request time and breaks extraction outright.

Surfaced end to end: the invoice card shows Vendor / Billed to / Payment details
sections and the full charge breakdown, and CSV export grew from 15 columns to
30. 16 tests follow a fully-populated invoice from model output through
normalize, storage, API and CSV.

*Still open:* no deterministic re-check of the model's arithmetic yet (that
belongs with the P1.2 validation engine), no OpenAI client timeout or retry, and
`purchase_order_reference` is not yet a denormalized column for matching.

### [ ] P1.2 Validation engine

Required-field checks (configurable per organization); financial checks
(line items → subtotal → tax → total, discounts, outstanding balance); date
checks (missing, malformed, due-before-invoice, suspiciously old); supplier
checks (missing, unknown, inconsistent naming, tax ID format).

Status: `valid` / `valid_with_warnings` / `requires_review` / `invalid`, each
warning carrying a specific human-readable explanation. **Validation never
mutates extracted figures.**

*Depends on F2.*

### [x] P1.3 Duplicate detection

Done. Four rules in `duplicates.py`, strongest first, with the first one that
fires for a pair being the one reported — so an identical file is flagged once
as an exact match rather than three times under three rules:

| Rule | Signal | Score |
|---|---|---|
| `exact_file` | SHA-256 of the uploaded bytes | 1.0 |
| `same_number` | Same supplier + invoice number | 0.95 |
| `same_amount_date` | Same supplier, total and invoice date | 0.8 |
| `similar` | Same supplier and amount a few days apart, or the same number under a differently-read supplier name | 0.55 |

Supplier names are normalized (case, punctuation and company-form suffixes
dropped, so "ACME Supplies Ltd." matches "acme supplies limited") and invoice
numbers compared ignoring separators ("INV-2026-001" = "inv2026001").

**Nothing is ever deleted, rejected or merged.** A supplier can legitimately
bill the same amount twice in a day, and refusing a real invoice is worse than
the error being prevented. Matches are recorded in `duplicate_matches` for a
human: *Yes, duplicate* records the decision and still deletes nothing;
*Not a duplicate* dismisses it permanently, because re-showing a warning
someone has already judged teaches them to ignore all of them.

Detection is organization-scoped — a match across tenants would not be a
duplicate, it would be a data leak. There is a test for that.

Surfaced as a panel above the validation verdict on the invoice card (if it may
already be paid, that outranks "the arithmetic is off"), with a Compare link to
the other document, plus `GET /api/duplicates` as a review queue.

24 tests, weighted as much toward *not* flagging genuine invoices as toward
catching real duplicates.

*Still open:* no fuzzy document-image comparison (rule 4 of the brief's
"potentially similar" is handled by name/amount/date proximity, not by
comparing the documents themselves), and the review queue has no dedicated page
yet.

Four levels: exact file duplicate (SHA-256 of the bytes — cheap, so do it
first); same supplier + invoice number; same supplier + amount + date; fuzzy
similarity. Flag for review, never auto-delete or auto-reject. Show both
documents side by side with the matching reason, upload dates and statuses, and
let an authorized user confirm or dismiss.

### [x] P1.4 Review experience

Done. Split-screen on the detail page: original document sticky on the left,
extracted fields on the right, stacking below xl where side-by-side would make
both halves unusable. A toggle switches to full-width fields.

**Audit trail.** Every manual change is recorded in `field_corrections` with
the original value, the new value, who, when and an optional reason. The
original is never overwritten - correcting a figure must not destroy the
evidence of what the document said. Paths identify the exact cell
(`line_items.2.unit_price`), not "line items changed".

Both sides are normalized before diffing, so changing `100` to `"100.00"` is
not recorded as an edit, and null vs "" is treated as the same absence -
otherwise re-saving an untouched form would manufacture a trail of phantom
edits and poison the signal these rows exist to provide. (Aggregated, they say
where extraction actually goes wrong, which is how the prompt gets improved.)

Editing marks the document reviewed, which feeds the "awaiting review" count.

14 tests.

*Still open:* no field-to-document highlighting - the `chat.completions`
pipeline returns no bounding boxes, so that needs a layout-aware OCR pass
(a cost and vendor decision, noted under Open Decisions).

Split-screen: original document left, extracted fields and validation results
right. Confidence indicators, validation and duplicate warnings, editable fields
and line items, reprocess, approve/reject. Field-to-document location
highlighting where source coordinates are available — note that the current
`chat.completions` pipeline returns no bounding boxes, so this needs either a
layout-aware OCR pass or acceptance that highlighting ships later.

Audit trail on every manual correction: original value, corrected value, user,
timestamp, optional reason.

### [x] P1.5 Processing history

Done. The list was a flat 300 rows with browser-side search, which meant that
past a few hundred documents the older ones were not just hidden but
**unsearchable** — the data was there and the user could not reach it.

Now server-side: search across file name, supplier and invoice number; filters
for processing status, validation status, document type, reviewed state,
supplier, currency, date range and amount range; sortable on six columns via an
allow-list (the key reaches `ORDER BY`, so it is never taken verbatim);
paginated at 25 with a hard cap of 100 per page.

Each row carries enough to triage without opening it — validation badge, issue
count, duplicate count, field count, processing time, uploader, and the error
message for a failed run. That needed denormalized columns
(`validation_status`, `validation_issue_count`, `extracted_field_count`,
`processing_ms`, `error_message`, `reviewed_at`), written whenever a document
is created or edited. Validation itself is still recomputed on read, so an
edited invoice always shows a current verdict; the column is the last known one
and exists so "show me everything needing review" is one SQL query rather than
loading and validating every row.

`GET /api/extractions/export` downloads the **currently filtered** rows as CSV —
what you see is what you export.

Adding `reviewed_by_user_id` gave `Extraction` two foreign keys to `users`, and
SQLAlchemy refused the ambiguous `User.extractions` join until it was told which
one to use. Worth knowing before adding a third.

24 tests.

*Still open:* no saved views, and Excel export of the history list (only CSV;
per-document XLSX already exists).

Columns: document, upload date, processing / extraction / validation / review
status, field count, warning count, duration, errors, uploader. Filters: date
range, status, supplier, currency, amount range. Server-side pagination and
search, replacing today's hard 300-row cap. CSV and Excel export.

### [x] P1.6 Usage reporting

Done. `GET /api/usage/stats` returns processed/failed/in-progress counts,
success rate, average processing time, awaiting-review and unresolved-duplicate
counts, a validation breakdown, a 30-day activity trend, and the plan
allowance.

The allowance comes from `usage.py` unchanged - the same code billing enforces.
A dashboard that said 94 while billing said 96 would make both numbers
worthless, and there is a test asserting the two endpoints agree exactly.

Some deliberate choices: the success rate excludes documents still running (a
rate that dips mid-extraction looks like a reliability problem that is not
happening) and is `null` rather than 0 before anything has finished. Average
time counts completed runs only, or one 300s timeout would dominate it.
"Awaiting review" excludes documents someone has already opened, and excludes
failures - those need re-running, not reviewing.

Shown as tiles on the dashboard; the action tiles only appear when there is
something to act on, since tiles reading zero teach people to stop looking.
They deep-link into History, which now reads its filters from the URL.

18 tests, including that failed and deleted documents do not distort the
allowance.

Uploaded / processed / failed / awaiting review, pages processed, monthly usage,
remaining allowance, average processing time, success rate. Must reconcile
exactly with billing. **Failed and retried jobs must not consume quota** — today
usage counts `status == "completed"`, which is correct, and F4's retry logic has
to preserve that.

### [~] P1.7 Pricing and subscription management

**Bachs migration — done. Paystack removed entirely.** `billing.py` and its test
suite are deleted; `bachs.py` is the only provider.

- Hosted subscription checkout with an `Idempotency-Key`, so a retried request
  cannot open two subscriptions.
- Webhook verification: HMAC-SHA256 over `timestamp.body`, `X-Bachs-Signature-V2`
  (accepting several `v1=` values during secret rotation) plus the legacy header
  pair, 300s replay window, constant-time comparison.
- `/billing/verify` for the return page (`?checkout_id=`), with an ownership
  check so a guessed id cannot upgrade the caller.
- `/billing/sync` reconciles entitlement from the provider's subscription
  records, and deliberately does **not** downgrade when every read fails — a
  provider outage must not cost a paying customer their plan.
- `/billing/cancel` and `/billing/subscription`, cancelling at period end.
- `provider_events` de-duplicates at-least-once delivery on the envelope id;
  `subscriptions` maps users to provider subscriptions, which is the only way a
  renewal invoice (no metadata of ours) can be attributed.

Access rules are taken from the docs, not guessed: revoke on
`customer.subscription.deleted` and on an `unpaid` status (where "mark unpaid"
accounts land after dunning); keep access through `past_due` and through a
scheduled `cancel_at_period_end`, because that period is paid for.

Money: amounts are decimal major units end to end. `Payment.amount` moved from
an integer of minor units to `Numeric(18, 4)`, with the migration converting
existing rows.

*Still to do:* plan *tiers* themselves (enterprise, per-seat, usage dimensions)
are untouched — only the provider changed. No cancel button in the UI yet,
though the endpoint exists. Sandbox verification against the real Bachs API has
not been run.


Plan tiers (free/trial, starter, professional, business, enterprise) with
dimensions: monthly allowance, users, organizations, pages, advanced validation,
duplicate detection, approval workflows, reporting, API, AI assistant.
Subscription status, upgrade/downgrade, billing history, payment-failure
handling, cancellation, renewal, usage notifications.

**Blocked on the Bachs migration — see Open Decisions.**

### [x] P1.8 Onboarding

Done. A setup checklist on the dashboard: confirm email, name the organization,
add business details, choose a plan, process a first document, review it.

**Derived, not stored.** The steps are computed from real state on every
request, so the checklist can go backwards - delete your only document and
"Process your first document" unticks itself, because it is true again. A
stored wizard position starts lying the moment anything changes underneath it.
The only thing persisted is `onboarding_dismissed_at`, which is a preference
and cannot be derived. Dismissing hides the panel without claiming the work was
done.

Business details and plan choice are optional and do not block completion -
requiring them would leave the checklist permanently unfinished for someone
happily on the free plan.

`GET/PATCH /api/organizations/current` manages the profile, validating country
and currency codes rather than storing nonsense that would quietly corrupt
reports later. Changing settings needs `organization:settings`; reading the
checklist does not.

23 tests.

Account → email verification → create organization → organization details →
plan or trial → first upload → review → dashboard orientation. Interactive first
upload, real empty states, contextual guidance.

*Depends on F3, since creating an organization is part of the flow.*

**Phase 1 acceptance:** a user uploads an invoice, gets structured data, reviews
it against the original, corrects errors, sees validation results, is warned
about duplicates, and can track processing history.

---

## Phase 2 — Financial operations / accounts payable

All of Phase 2 depends on **F3**.

- **[ ] P2.1 Supplier management** — full supplier records (including bank
  details behind access control), automatic association from extracted
  invoices, history, invoiced totals, outstanding balances, and duplicate
  supplier detection.
- **[ ] P2.2 Purchase orders** — create, assign supplier, line items, taxes,
  delivery dates, terms, attachments, approval submission. Statuses: draft,
  pending approval, approved, sent to supplier, partially received, fully
  received, closed, cancelled. Downloadable PDF.
- **[ ] P2.3 Invoice-to-PO matching** — match on supplier and PO reference, then
  compare line items, quantities, unit prices, taxes and totals. Report exact
  matches, price and quantity discrepancies, missing references, supplier
  mismatches and over-PO invoicing. Configurable tolerances. Never auto-approve
  an invoice that fails an important check.
- **[ ] P2.4 Goods received + three-way matching** — GRN records with ordered /
  received / damaged / outstanding quantities and partial deliveries, then
  PO + GRN + Invoice matching. Detect invoice-before-goods, over-invoicing
  against delivery, and quantity or amount mismatches.
- **[ ] P2.5 Approval workflows** — rules by amount, department, supplier,
  category, project, cost centre and PO status. Single and multi-level,
  sequential and parallel, delegation, rejection with comments, information
  requests, reminders, full history, notifications. Configurable, not hardcoded.
- **[ ] P2.6 Payment tracking** — invoice amount, paid, outstanding, due date,
  status (unpaid / partially paid / paid / overdue / disputed), payment date,
  reference, method. Manual recording. Architected for later payment
  integrations while **initiating no payments**.
- **[ ] P2.7 Bank reconciliation** — CSV/Excel statement import, matching by
  exact / amount / date / reference / fuzzy description, surfacing unmatched,
  duplicate, partial and discrepant transactions, a manual reconciliation UI,
  fully auditable. A statement *extraction* path already exists
  (`statement_schema.py`) and should be reused rather than duplicated.

**Phase 2 acceptance:** a business runs invoice → approval → payment recording,
and reconciles payments against imported bank transactions.

---

## Phase 3 — Mobile application

The technology recommendation is deferred until Phase 2 is stable. The backend is
a plain JSON API with JWT, so **React Native** is the lower-friction choice given
the team already works in React, with Flutter the alternative if native feel
matters more than code reuse. Decide at the time, not now.

Mobile consumes the **same APIs and business rules** — no financial logic is
reimplemented client-side.

- **[ ] P3.1** Auth, registration, password reset, email verification, session
  and secure token handling, and organization switching that is strictly scoped.
- **[ ] P3.2** Camera and gallery capture, multi-page scanning, crop and rotate,
  preview, client-side compression, tolerance for poor lighting and skew.
- **[ ] P3.3** Extraction results: status, fields, supplier, totals, line items,
  validation and duplicate warnings, confidence, inline editing.
- **[ ] P3.4** Mobile review: document preview, edit, warnings, confirm, submit
  for approval.
- **[ ] P3.5** Push notifications (approval needed, approved, rejected, overdue,
  unusual activity) and in-app approve/reject with authentication and audit
  logging.
- **[ ] P3.6** Voice-assisted queries (speech-to-text and text-to-speech),
  enforcing exactly the same permissions as text queries.

---

## Phase 4 — Financial intelligence

- **[ ] P4.1 Spending analytics** — totals by period, supplier, category,
  department, project and currency; tax spend; outstanding liabilities;
  interactive charts and filters. **All figures computed in SQL, never by an LLM.**
- **[ ] P4.2 Supplier performance** — purchase totals, average invoice,
  frequency, payment history, late submissions, price variation, outstanding
  balances and disputes; flag unusual price movements and recurring
  discrepancies.
- **[ ] P4.3 Outstanding payment intelligence** — an AP dashboard with unpaid,
  overdue, due within 7 and 30 days, supplier balances, and aging buckets
  (current, 1–30, 31–60, 61–90, 90+), each drilling down to the underlying
  invoices.
- **[ ] P4.4 Anomaly detection** — explainable rules first (duplicates, unusual
  amounts, sudden price rises, repeated invoice numbers, odd payment patterns,
  supplier bank-detail changes, out-of-pattern spend, over-PO invoices,
  suspicious tax), with statistical methods only once there is history. Labels
  are "unusual activity" / "requires investigation" / "potential duplicate" /
  "financial discrepancy" — **never "fraudulent"** — each with its supporting
  evidence.
- **[ ] P4.5 AI financial assistant** — natural-language queries over the
  organization's data. The LLM **never gets database access**: authenticate →
  resolve organization → check permissions → interpret the question → map it to
  an approved parameterized query or predefined analytical operation → execute
  tenant-scoped → retrieve rows → have the LLM explain the result. Deterministic
  figures, with links to source records. Conversation context never widens
  permissions.

---

## Cross-cutting requirements (apply to every step above)

**Database** — indexes on every foreign key and filter column, FK constraints,
explicit transactions, `Numeric` for money, explicit currency codes, consistent
UTC storage with timezone-aware conversion, soft deletion where appropriate,
audit trails, and database-level integrity constraints.

**Security** — tenant isolation above all; RBAC; secure document storage behind
authorization checks and short-lived signed URLs; file type and size validation;
malware scanning where available; rate limiting; input validation; SQLi, XSS and
CSRF protection; secure password and API-token handling; audit logging; no
supplier bank details to unauthorized users; and no confidential records leaking
into AI prompts.

**UI/UX** — reference Ramp, BILL, Brex, Airbase, Dext and Hubdoc as inspiration,
not templates. Clean hierarchy, professional tables, responsive, accessible, with
real loading, empty and error states. **Navigation exposes only implemented
features** — no dead menu items.

**API** — consistent endpoints, a validation layer, auth, tenant permissions,
pagination, filtering, search, uniform errors and documentation. Retain Flask;
do not add a second backend for mobile.

**Background processing** — async for OCR, extraction, conversion, large uploads,
duplicate analysis, report generation, statement processing and notifications,
with retries, status tracking, idempotency, timeouts, monitoring and queue
separation. Cache expensive analytics without ever serving stale or cross-tenant
data.

**Testing** — unit (parsing, financial calculations, validation, duplicates, PO
matching, GRN math, approval rules, payments, reconciliation, permissions),
integration (upload → extraction → validation → review → matching → approval →
reconciliation → AI queries), security (cross-tenant access, unauthorized
approval, document access, data exposure) and frontend (forms, uploads, review,
dashboards, filters, tables, responsive layouts, error states). A rendered
interface is not a working feature.

**Process** — inspect before modifying; extend rather than rewrite; work in
milestones and report what changed, which files, which schema changes, which
endpoints and which tests pass or fail; review every migration and never make a
destructive schema change without a stated safe strategy; keep secrets in
environment variables and update `.env.example` and the deployment docs; ship no
non-functional UI; compute financial figures deterministically; and maintain the
README, architecture, API, database, setup, deployment and testing docs.

---

## Open decisions (needed from the product owner)

1. **Bachs migration (blocks P1.7).** Billing is entirely Paystack-shaped:
   HMAC-SHA512 webhook verification keyed on the secret key, auto-provisioned
   `PLN_` plan codes, `charge.success` / `subscription.disable` event mapping,
   and kobo/cents amounts. Moving to Bachs needs their API documentation —
   webhook signature scheme, event names, subscription model. Recommended shape:
   a provider interface behind the existing four functions (`is_configured`,
   `create_checkout`, `verify_transaction`, `verify_webhook`), which is all
   `billing_routes.py` consumes.
2. **Multi-tenancy timing (F3).** Recommended before Phase 1 feature work.
   Doing Phase 1 first on the per-user model means rewriting it later.
3. **Production data state.** How many live accounts and extractions exist? This
   determines whether the F2 and F3 backfills can run in a single migration
   window or need an online backfill.
4. **Field highlighting (P1.4).** Source coordinates need a layout-aware OCR pass
   (Textract, Document AI, Azure DI) alongside the current LLM extraction, or the
   feature ships later. This is a cost and vendor decision.

---

## Previously shipped

<details><summary>Receipt support — SHIPPED</summary>

Receipts are a first-class document type alongside invoices: a type toggle on
upload, a dedicated receipt schema (merchant, date, payment method, category,
tip, totals + confidence), a `ReceiptCard`, expense-friendly CSV, and history
labelling. Bank statements later followed the same pattern
(`statement_schema.py`).

</details>

Still open from the original roadmap:

- **Receipt-specific marketing pages** — a `/use-cases/receipts` page and a
  "receipt OCR" post in `content/registry.js` (auto-flows into the sitemap and
  prerender).
- **QuickBooks API sync** — true one-click push (OAuth + API) instead of CSV
  import.
