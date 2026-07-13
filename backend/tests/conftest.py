"""Shared pytest fixtures.

Each test gets a fresh app backed by a temporary SQLite file, with external
services (OpenAI, Resend email) stubbed so nothing leaves the machine. Rate
limiting is off by default — the rate-limit test opts back in explicitly.
"""
import os

import pytest

from config import Config


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_ENGINE_OPTIONS = {}
    RATELIMIT_ENABLED = False
    RATELIMIT_STORAGE_URI = "memory://"
    PROXY_HOPS = 0
    JWT_SECRET = "test-secret-key"
    OPENAI_API_KEY = "test-openai-key"
    RESEND_API_KEY = ""  # _send() short-circuits when empty
    PAYSTACK_SECRET_KEY = ""
    APP_URL = "http://localhost:5173"
    FRONTEND_ORIGIN = "http://localhost:5173"


@pytest.fixture
def app(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    TestConfig.SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_file}"
    TestConfig.UPLOAD_DIR = str(tmp_path / "uploads")
    os.makedirs(TestConfig.UPLOAD_DIR, exist_ok=True)

    # Never send real emails in tests.
    import routes.auth_routes as ar
    monkeypatch.setattr(ar, "send_verification", lambda *a, **k: True)
    monkeypatch.setattr(ar, "send_password_reset", lambda *a, **k: True)

    # Keep tests hermetic regardless of the developer's .env: billing reads the
    # module-level Config, so default it to demo mode (specific billing tests
    # override this). The plan codes come from os.getenv, so clear them too.
    monkeypatch.setattr("config.Config.PAYSTACK_SECRET_KEY", "", raising=False)
    for env_key in ("PAYSTACK_PLAN_STARTER", "PAYSTACK_PLAN_PRO", "PAYSTACK_PLAN_BUSINESS"):
        monkeypatch.delenv(env_key, raising=False)

    from app import create_app
    from extensions import db

    application = create_app(TestConfig)
    with application.app_context():
        db.drop_all()
        db.create_all()
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


# ─── Helpers ─────────────────────────────────────────────────────────────────
def make_user(app, email="user@example.com", plan="free", verified=True, password="password123"):
    """Create a user directly in the DB and return it (detached id/email/plan)."""
    from extensions import db
    from models import User
    from auth import hash_password

    with app.app_context():
        u = User(
            email=email,
            name="Test",
            password_hash=hash_password(password),
            plan=plan,
            email_verified=verified,
        )
        db.session.add(u)
        db.session.commit()
        return {"id": u.id, "email": u.email, "plan": u.plan}


def auth_header(app, user):
    from models import User
    from auth import issue_token

    with app.app_context():
        u = User.query.get(user["id"])
        return {"Authorization": f"Bearer {issue_token(u)}"}
