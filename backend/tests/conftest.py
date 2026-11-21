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
    BACHS_SECRET_KEY = ""
    BACHS_WEBHOOK_SECRET = ""
    # The demo-billing tests exercise unpaid plan switching, which is now
    # opt-in. test_billing covers what happens with it off.
    BILLING_DEMO_MODE = True
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

    # Keep tests hermetic regardless of the developer's .env: config.py calls
    # load_dotenv(), so a real BACHS_SECRET_KEY (a live key that moves real
    # money) would otherwise make bachs.is_configured() true during the run and
    # in principle let a test reach the live API. Tests that want the provider
    # set these explicitly.
    monkeypatch.setattr("config.Config.BACHS_SECRET_KEY", "", raising=False)
    monkeypatch.setattr("config.Config.BACHS_WEBHOOK_SECRET", "", raising=False)

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
def make_user(app, email="user@example.com", plan="free", verified=True,
              password="password123", role=None):
    """Create a user with a personal organization, and return both.

    `plan` is set on the ORGANIZATION, which is where it lives — a team shares
    one allowance. The returned dict keeps a "plan" key for convenience, but it
    reflects the organization.
    """
    from auth import hash_password
    from extensions import db
    from models import User
    from tenancy import ensure_personal_organization

    with app.app_context():
        u = User(
            email=email,
            name="Test",
            password_hash=hash_password(password),
            email_verified=verified,
        )
        db.session.add(u)
        db.session.flush()
        org = ensure_personal_organization(u, plan=plan)
        if role:
            from models import OrganizationMembership
            membership = OrganizationMembership.query.filter_by(
                user_id=u.id, organization_id=org.id
            ).first()
            membership.role = role
        db.session.commit()
        return {
            "id": u.id,
            "email": u.email,
            "plan": org.plan,
            "organization_id": org.id,
        }


def make_org(app, owner, name="Shared org", plan="free"):
    """Create a second, non-personal organization owned by `owner`."""
    from extensions import db
    from models import Organization, OrganizationMembership
    from roles import OWNER

    with app.app_context():
        org = Organization(name=name, is_personal=False, plan=plan)
        db.session.add(org)
        db.session.flush()
        db.session.add(OrganizationMembership(
            organization_id=org.id, user_id=owner["id"], role=OWNER,
        ))
        db.session.commit()
        return {"id": org.id, "plan": org.plan, "name": org.name}


def join_org(app, org, user, role):
    """Add `user` to `org` with `role`."""
    from extensions import db
    from models import OrganizationMembership

    with app.app_context():
        db.session.add(OrganizationMembership(
            organization_id=org["id"], user_id=user["id"], role=role,
        ))
        db.session.commit()


def org_header(app, user, org):
    """Auth header that acts as `org` rather than the user's personal one."""
    headers = auth_header(app, user)
    headers["X-Organization-Id"] = org["id"]
    return headers


def auth_header(app, user):
    from auth import issue_token
    from models import User

    with app.app_context():
        u = User.query.get(user["id"])
        return {"Authorization": f"Bearer {issue_token(u)}"}
