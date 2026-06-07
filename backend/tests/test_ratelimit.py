"""Rate limiting on auth endpoints (opt-in: most tests run with it disabled)."""
import os

from config import Config


def _enabled_app(tmp_path, monkeypatch):
    class RLConfig(Config):
        TESTING = True
        SQLALCHEMY_ENGINE_OPTIONS = {}
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path/'rl.db'}"
        UPLOAD_DIR = str(tmp_path / "uploads")
        JWT_SECRET = "test"
        RESEND_API_KEY = ""
        RATELIMIT_ENABLED = True
        RATELIMIT_STORAGE_URI = "memory://"
        RATELIMIT_AUTH = "5 per minute"

    os.makedirs(RLConfig.UPLOAD_DIR, exist_ok=True)
    import routes.auth_routes as ar
    monkeypatch.setattr(ar, "send_verification", lambda *a, **k: True)

    from app import create_app
    from extensions import db
    app = create_app(RLConfig)
    with app.app_context():
        db.drop_all()
        db.create_all()
    return app


def test_auth_endpoint_rate_limited(tmp_path, monkeypatch):
    app = _enabled_app(tmp_path, monkeypatch)
    client = app.test_client()

    codes = [
        client.post("/api/auth/login", json={"email": "x@y.com", "password": "z"}).status_code
        for _ in range(7)
    ]
    # First 5 allowed (401 invalid creds), then the limiter kicks in with 429.
    assert codes[:5] == [401] * 5
    assert 429 in codes[5:]
