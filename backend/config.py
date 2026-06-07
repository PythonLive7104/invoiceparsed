"""Application configuration, loaded from environment variables (.env)."""
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    # Auth
    JWT_SECRET = os.getenv("JWT_SECRET", "change-me")
    JWT_EXP_DAYS = 30

    # Database — prefer the Supabase Postgres pooler if set, else DATABASE_URL,
    # else local SQLite. SQLAlchemy needs the "postgresql://" scheme (Supabase
    # may hand out "postgres://"), so normalise it.
    _db_url = os.getenv("SUPABASE_URL") or os.getenv("DATABASE_URL", "sqlite:///invoiceparsed.db")
    if _db_url.startswith("postgres://"):
        _db_url = _db_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # pgBouncer (Supabase pooler, port 6543) is transaction-mode; pre-ping avoids
    # handing out dead connections, and we don't keep our own large pool.
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # OpenAI
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

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

    # Dodo Payments. Leave DODO_API_KEY blank to run billing in demo mode (plan
    # changes apply instantly, no real payment). Set all values for production.
    DODO_API_KEY = os.getenv("DODO_API_KEY", "")
    DODO_API_BASE = os.getenv("DODO_API_BASE", "https://test.dodopayments.com")
    DODO_WEBHOOK_SECRET = os.getenv("DODO_WEBHOOK_SECRET", "")

    # Uploads
    MAX_CONTENT_LENGTH = 64 * 1024 * 1024  # request body cap (allows several pages)
    MAX_FILE_BYTES = 10 * 1024 * 1024      # 10MB per file, per the PRD
    UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(BASE_DIR, "uploads"))

    # Rate limiting (Flask-Limiter). In production point storage at Redis, e.g.
    # RATELIMIT_STORAGE_URI=redis://localhost:6379, so limits are shared across
    # gunicorn workers. Defaults to in-process memory for dev.
    RATELIMIT_ENABLED = os.getenv("RATELIMIT_ENABLED", "true").lower() == "true"
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_DEFAULT = os.getenv("RATELIMIT_DEFAULT", "300 per minute")
    # Tighter budget for unauthenticated/credential endpoints (per IP).
    RATELIMIT_AUTH = os.getenv("RATELIMIT_AUTH", "10 per minute")

    # Webhooks
    WEBHOOK_TIMEOUT = 6  # seconds per delivery attempt
    WEBHOOK_MAX_ATTEMPTS = int(os.getenv("WEBHOOK_MAX_ATTEMPTS", "4"))  # total tries
    WEBHOOK_BACKOFF_BASE = float(os.getenv("WEBHOOK_BACKOFF_BASE", "2"))  # seconds; *2^n
    WEBHOOK_BACKOFF_CAP = float(os.getenv("WEBHOOK_BACKOFF_CAP", "60"))  # max sleep between tries
    API_KEY_PREFIX = "ip_live_"
