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

    # Uploads
    MAX_CONTENT_LENGTH = 64 * 1024 * 1024  # request body cap (allows several pages)
    MAX_FILE_BYTES = 10 * 1024 * 1024      # 10MB per file, per the PRD
    UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(BASE_DIR, "uploads"))

    # Webhooks
    WEBHOOK_TIMEOUT = 6  # seconds per delivery attempt
    API_KEY_PREFIX = "ip_live_"
