"""Application configuration, loaded from environment variables (.env)."""
import os

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    # Auth
    JWT_SECRET = os.getenv("JWT_SECRET", "change-me")
    JWT_EXP_DAYS = 30
    # Flask session/CSRF secret (used by Flask-Admin forms). Reuses JWT_SECRET.
    SECRET_KEY = os.getenv("SECRET_KEY") or os.getenv("JWT_SECRET", "change-me")

    # Flask-Admin (/admin). Protected by HTTP Basic Auth with these credentials.
    # Leave either blank to disable the admin entirely.
    ADMIN_USER = os.getenv("ADMIN_USER", "")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

    # Database — DATABASE_URL wins. In the Docker deploy that's the bundled
    # Postgres container (see docker-compose.yml), which is the default setup.
    # SUPABASE_URL is kept as a fallback so an existing managed-Postgres install
    # keeps working untouched; set DATABASE_URL to move off it. Falls back to
    # local SQLite for host-only dev. SQLAlchemy needs the "postgresql://"
    # scheme (Supabase and some providers hand out "postgres://"), so normalise.
    _db_url = (
        os.getenv("DATABASE_URL")
        or os.getenv("SUPABASE_URL")
        or "sqlite:///invoiceparsed.db"
    )
    # Postgres URL hygiene, applied to whatever form was supplied:
    #   1. Some providers hand out "postgres://"; SQLAlchemy wants "postgresql://".
    #   2. Pin the DBAPI to psycopg2 — the driver requirements.txt installs.
    #      SQLAlchemy 2.1 changed the default for a driver-less "postgresql://"
    #      from psycopg2 to psycopg (v3), which isn't installed, so without this
    #      the app dies at startup on "No module named 'psycopg'".
    # A URL that names its own driver (postgresql+psycopg://, +asyncpg, …) is
    # left alone.
    if _db_url.startswith("postgres://"):
        _db_url = "postgresql://" + _db_url[len("postgres://"):]
    if _db_url.startswith("postgresql://"):
        _db_url = "postgresql+psycopg2://" + _db_url[len("postgresql://"):]
    SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # pre-ping checks a pooled connection before handing it out, so the app
    # recovers on its own when the database restarts (a `docker compose up -d db`
    # or a nightly backup hiccup) instead of serving one round of 500s. Also what
    # makes a transaction-mode pooler (pgBouncer / the Supabase pooler on 6543)
    # usable. Cheap: one round-trip per checkout, and we keep no large pool.
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    # Create any missing tables straight from the models at startup.
    #
    # Convenient for host-only dev and the test suite, but WRONG for a database
    # that holds real rows: create_all() only ever creates missing *tables*. It
    # never adds a column, changes a type or backfills, so a model change would
    # appear to deploy cleanly and then fail at runtime on the missing column.
    # The Docker deploy therefore sets this false and runs `flask db upgrade`
    # (Alembic) before gunicorn starts — see migrations/ and DEPLOY.md.
    AUTO_CREATE_TABLES = os.getenv("AUTO_CREATE_TABLES", "true").lower() == "true"

    # OpenAI
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    # Default extraction model. gpt-4o-mini is far cheaper; override per document
    # type below (e.g. keep statements on gpt-4o if mini's accuracy drops).
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    MODEL_INVOICE = os.getenv("MODEL_INVOICE", OPENAI_MODEL)
    MODEL_RECEIPT = os.getenv("MODEL_RECEIPT", OPENAI_MODEL)
    MODEL_STATEMENT = os.getenv("MODEL_STATEMENT", OPENAI_MODEL)

    # Where the contact form sends messages.
    CONTACT_TO = os.getenv("CONTACT_TO", "invoiceparsed@gmail.com")

    # ─── Try-before-signup demo ──────────────────────────────────────────────
    # Lets a visitor extract a document on the landing page with no account. The
    # result is shown in full but exports are gated behind signup; the extraction
    # is held server-side so the new account can claim it instead of re-uploading.
    DEMO_ENABLED = os.getenv("DEMO_ENABLED", "true").lower() == "true"
    # Hard per-IP lifetime cap (durable, survives restarts — see DemoUsage).
    DEMO_FREE_EXTRACTIONS = int(os.getenv("DEMO_FREE_EXTRACTIONS", "1"))
    # Unclaimed demo results (and their uploaded files) are purged after this long.
    DEMO_RETENTION_HOURS = int(os.getenv("DEMO_RETENTION_HOURS", "24"))
    # Burst limit on the demo endpoint, on top of the per-IP cap above.
    RATELIMIT_DEMO = os.getenv("RATELIMIT_DEMO", "6 per hour")

    # Rate limits for support endpoints (per IP).
    RATELIMIT_CHAT = os.getenv("RATELIMIT_CHAT", "20 per minute")
    RATELIMIT_CONTACT = os.getenv("RATELIMIT_CONTACT", "5 per minute")

    # Number of reverse-proxy hops to trust for X-Forwarded-* (real client IP +
    # scheme). 1 = behind nginx only (default Docker). 2 = behind Caddy → nginx
    # (the TLS setup). 0 = no proxy / exposed directly.
    PROXY_HOPS = int(os.getenv("PROXY_HOPS", "1"))

    # CORS — comma-separated list of allowed frontend origins
    FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")

    # Public URL of the frontend (used to build links in emails)
    APP_URL = os.getenv("APP_URL", FRONTEND_ORIGIN.split(",")[0].strip())

    # Google OAuth (Google Identity Services). The client ID is also used on the
    # frontend; the backend verifies that ID tokens were issued for it.
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")

    # Resend (transactional email)
    RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
    RESEND_FROM = os.getenv("RESEND_FROM", "InvoiceParsed <onboarding@resend.dev>")

    # Sentry error monitoring. Leave SENTRY_DSN blank to disable (dev/tests).
    SENTRY_DSN = os.getenv("SENTRY_DSN", "")
    SENTRY_ENVIRONMENT = os.getenv("SENTRY_ENVIRONMENT", "production")
    SENTRY_TRACES_SAMPLE_RATE = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0"))

    # Instant, unpaid plan switching for local development and the hosted demo.
    #
    # MUST be opt-in. This used to be inferred from "no payment provider is
    # configured", which conflated a deliberate dev setup with a production
    # misconfiguration: removing or rotating out a provider key silently turned
    # the billing endpoints into a free upgrade to any plan. Defaulting to false
    # means a missing provider now fails closed - plan changes are refused -
    # rather than giving the product away.
    BILLING_DEMO_MODE = os.getenv("BILLING_DEMO_MODE", "false").lower() == "true"

    # ─── Bachs (payment provider) ────────────────────────────────────────────
    # Leave BACHS_SECRET_KEY blank to disable. Differs from Paystack in three
    # ways that matter: webhooks are signed with a SEPARATE per-endpoint secret
    # (not the API key), amounts are decimal strings in major units (not minor
    # units), and there is no "plan" object — a recurring product id stands in
    # for a plan code.
    BACHS_SECRET_KEY = os.getenv("BACHS_SECRET_KEY", "")
    # From Developer Portal > Webhooks > <endpoint> > Signing secret. Without it
    # deliveries cannot be verified and are refused.
    BACHS_WEBHOOK_SECRET = os.getenv("BACHS_WEBHOOK_SECRET", "")
    # Live is https://api.bachs.io; sandbox is https://sandbox-api.bachs.io. A
    # key only works against its own environment, so these must agree: an
    # sk_sandbox_ key against the live base URL returns 401.
    BACHS_API_BASE = os.getenv("BACHS_API_BASE", "https://api.bachs.io")
    # Replay window for webhook timestamps, in seconds. Bachs' own samples use
    # 300; deliveries outside the window are refused.
    BACHS_WEBHOOK_TOLERANCE = int(os.getenv("BACHS_WEBHOOK_TOLERANCE", "300"))
    # Recurring product ids, one per paid tier (Bachs has no plan codes). Create
    # them once in the dashboard with a monthly billing_cycle.
    BACHS_PRODUCTS = {
        "starter": os.getenv("BACHS_PRODUCT_STARTER", ""),
        "pro": os.getenv("BACHS_PRODUCT_PRO", ""),
        "business": os.getenv("BACHS_PRODUCT_BUSINESS", ""),
    }

    # Uploads
    MAX_CONTENT_LENGTH = 64 * 1024 * 1024  # request body cap (allows several pages)
    MAX_FILE_BYTES = 10 * 1024 * 1024      # 10MB per file, per the PRD
    UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(BASE_DIR, "uploads"))
    # Hard cap on how many files may be submitted as the pages of ONE document.
    # Every page is another base64 image/PDF inside the same model request, so an
    # uncapped page count is an uncapped bill for a single call — the body cap
    # above alone would wave through roughly six full-size files.
    MAX_PAGES_PER_DOC = int(os.getenv("MAX_PAGES_PER_DOC", "10"))

    # Rate limiting (Flask-Limiter). In production point storage at Redis, e.g.
    # RATELIMIT_STORAGE_URI=redis://localhost:6379, so limits are shared across
    # gunicorn workers. Defaults to in-process memory for dev.
    RATELIMIT_ENABLED = os.getenv("RATELIMIT_ENABLED", "true").lower() == "true"
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_DEFAULT = os.getenv("RATELIMIT_DEFAULT", "300 per minute")
    # Tighter budget for unauthenticated/credential endpoints (per IP).
    RATELIMIT_AUTH = os.getenv("RATELIMIT_AUTH", "10 per minute")
    # Per-ACCOUNT ceiling on /api/extract. This is a cost control, not an abuse
    # control: every allowed call spends an OpenAI vision request, and the Pro and
    # Business plans have no monthly document limit at all, so under the 300/min
    # default a single scripted account could run up a very large bill in minutes.
    # Keyed on the account (see auth.rate_limit_key) rather than the IP, so one
    # account cannot multiply its budget by spreading calls across addresses.
    RATELIMIT_EXTRACT = os.getenv("RATELIMIT_EXTRACT", "20 per minute")

    # Webhooks
    WEBHOOK_TIMEOUT = 6  # seconds per delivery attempt
    WEBHOOK_MAX_ATTEMPTS = int(os.getenv("WEBHOOK_MAX_ATTEMPTS", "4"))  # total tries
    WEBHOOK_BACKOFF_BASE = float(os.getenv("WEBHOOK_BACKOFF_BASE", "2"))  # seconds; *2^n
    WEBHOOK_BACKOFF_CAP = float(os.getenv("WEBHOOK_BACKOFF_CAP", "60"))  # max sleep between tries
    # Webhook URLs are customer-supplied and fetched from inside our network, so
    # hosts resolving to private/loopback/link-local addresses are refused (see
    # webhooks.assert_safe_url) — that's the Postgres and Redis containers, the
    # API itself, and the cloud metadata endpoint. Set true ONLY for local
    # development against a webhook receiver on your own machine.
    WEBHOOK_ALLOW_PRIVATE_HOSTS = (
        os.getenv("WEBHOOK_ALLOW_PRIVATE_HOSTS", "false").lower() == "true"
    )
    API_KEY_PREFIX = "ip_live_"
