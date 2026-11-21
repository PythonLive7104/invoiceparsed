"""Rate limiting on auth + demo endpoints (opt-in: most tests run with it disabled)."""
import io
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
        RATELIMIT_DEMO = "2 per hour"
        RATELIMIT_EXTRACT = "2 per minute"
        OPENAI_API_KEY = "test-key"
        # High enough that a 429 can only come from the limiter, not the per-IP cap.
        DEMO_FREE_EXTRACTIONS = 5

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


def test_demo_endpoint_rate_limited(tmp_path, monkeypatch):
    """The demo is unauthenticated and spends money per call, so the burst limit
    on it has to actually fire. (Its limit is read from config at request time,
    which the rest of the suite never exercises.)"""
    app = _enabled_app(tmp_path, monkeypatch)

    import routes.demo_routes as dr
    monkeypatch.setattr(dr, "extract_document", lambda pages, doc_type="invoice": {
        "vendor": {"name": "Acme", "address": None, "email": None},
        "invoice_number": "INV-1", "invoice_date": None, "due_date": None,
        "currency": "USD", "payment_terms": None, "line_items": [],
        "subtotal": None, "tax": None, "total": 10.0,
        "confidence": {k: 1.0 for k in (
            "vendor", "invoice_number", "invoice_date", "due_date", "currency",
            "payment_terms", "line_items", "subtotal", "tax", "total")},
    })

    client = app.test_client()
    codes = [
        client.post(
            "/api/demo/extract",
            data={"file": (io.BytesIO(b"fake-image-bytes"), "inv.png")},
            content_type="multipart/form-data",
        ).status_code
        for _ in range(3)
    ]
    assert codes[:2] == [200, 200]
    assert codes[2] == 429


def _stub_extract(monkeypatch):
    import routes.extract_routes as er
    monkeypatch.setattr(er, "extract_document", lambda pages, doc_type="invoice": {
        "vendor": {"name": "Acme", "address": None, "email": None},
        "invoice_number": "INV-1", "invoice_date": None, "due_date": None,
        "currency": "USD", "payment_terms": None, "line_items": [],
        "subtotal": None, "tax": None, "total": 10.0,
        "confidence": {k: 1.0 for k in (
            "vendor", "invoice_number", "invoice_date", "due_date", "currency",
            "payment_terms", "line_items", "subtotal", "tax", "total")},
    })


def _png():
    return (io.BytesIO(b"fake-png-bytes"), "invoice.png")


def test_extract_rate_limited_per_account(tmp_path, monkeypatch):
    """An unlimited plan still must not be able to spend unbounded OpenAI calls."""
    app = _enabled_app(tmp_path, monkeypatch)
    _stub_extract(monkeypatch)

    from tests.conftest import auth_header, make_user
    user = make_user(app, email="pro@example.com", plan="pro")  # plan limit: None
    headers = auth_header(app, user)
    client = app.test_client()

    codes = [
        client.post(
            "/api/extract",
            data={"file": _png()},
            headers=headers,
            content_type="multipart/form-data",
        ).status_code
        for _ in range(3)
    ]
    assert codes[:2] == [200, 200]
    assert codes[2] == 429


def test_extract_limit_is_not_shared_between_accounts(tmp_path, monkeypatch):
    """Keyed on the account, so one user burning their budget must not lock out
    another user behind the same IP (the test client always presents one IP)."""
    app = _enabled_app(tmp_path, monkeypatch)
    _stub_extract(monkeypatch)

    from tests.conftest import auth_header, make_user
    noisy = make_user(app, email="noisy@example.com", plan="pro")
    quiet = make_user(app, email="quiet@example.com", plan="pro")
    client = app.test_client()

    for _ in range(3):
        client.post(
            "/api/extract",
            data={"file": _png()},
            headers=auth_header(app, noisy),
            content_type="multipart/form-data",
        )

    r = client.post(
        "/api/extract",
        data={"file": _png()},
        headers=auth_header(app, quiet),
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
