"""Try-before-signup demo: per-IP cap, gating, and claiming into an account."""
import io
import json

from tests.conftest import make_user, auth_header

FAKE_INVOICE = {
    "vendor": {"name": "Acme", "address": None, "email": None},
    "invoice_number": "INV-1", "invoice_date": None, "due_date": None,
    "currency": "USD", "payment_terms": None, "line_items": [],
    "subtotal": None, "tax": None, "total": 10.0,
    "confidence": {k: 1.0 for k in (
        "vendor", "invoice_number", "invoice_date", "due_date", "currency",
        "payment_terms", "line_items", "subtotal", "tax", "total")},
}


def _file(name="invoice.png", content=b"\x89PNG\r\n\x1a\nfake"):
    return (io.BytesIO(content), name)


def _stub_extract(monkeypatch, fn=None):
    import routes.demo_routes as dr
    monkeypatch.setattr(
        dr, "extract_document", fn or (lambda pages, doc_type="invoice": FAKE_INVOICE)
    )


def _post(client, **extra):
    data = {"file": _file(), **extra}
    return client.post("/api/demo/extract", data=data, content_type="multipart/form-data")


# ─── Status ──────────────────────────────────────────────────────────────────
def test_status_reports_a_free_extraction_available(client, app, monkeypatch):
    monkeypatch.setitem(app.config, "OPENAI_API_KEY", "test-key")
    r = client.get("/api/demo/status")
    assert r.status_code == 200
    body = r.get_json()
    assert body["enabled"] is True
    assert body["remaining"] == body["limit"] == 1
    assert body["used"] == 0
    assert "statement" not in body["docTypes"]


def test_status_disabled_without_an_openai_key(client, app, monkeypatch):
    monkeypatch.setitem(app.config, "OPENAI_API_KEY", "")
    assert client.get("/api/demo/status").get_json()["enabled"] is False


# ─── Extraction ──────────────────────────────────────────────────────────────
def test_demo_extract_needs_no_account(client, app, monkeypatch):
    _stub_extract(monkeypatch)
    r = _post(client)  # no Authorization header
    assert r.status_code == 200
    body = r.get_json()
    assert body["invoice"]["vendor"]["name"] == "Acme"
    assert body["docType"] == "invoice"
    assert body["claimToken"]
    assert body["demo"]["remaining"] == 0


def test_second_attempt_from_same_ip_is_refused(client, app, monkeypatch):
    _stub_extract(monkeypatch)
    assert _post(client).status_code == 200
    r = _post(client)
    assert r.status_code == 402
    assert r.get_json()["code"] == "DEMO_LIMIT_REACHED"


def test_failed_extraction_still_consumes_the_attempt(client, app, monkeypatch):
    """A costly-but-failed model call must not be retryable for free."""
    def boom(pages, doc_type="invoice"):
        raise RuntimeError("model exploded")

    _stub_extract(monkeypatch, boom)
    assert _post(client).status_code == 502
    assert client.get("/api/demo/status").get_json()["remaining"] == 0


def test_statements_are_not_offered_in_the_demo(client, app, monkeypatch):
    """doc_type=statement silently falls back to invoice rather than running the
    most expensive extraction for an anonymous visitor."""
    seen = {}

    def spy(pages, doc_type="invoice"):
        seen["doc_type"] = doc_type
        return FAKE_INVOICE

    _stub_extract(monkeypatch, spy)
    r = _post(client, doc_type="statement")
    assert r.status_code == 200
    assert seen["doc_type"] == "invoice"
    assert r.get_json()["docType"] == "invoice"


def test_multi_file_is_refused(client, app, monkeypatch):
    _stub_extract(monkeypatch)
    r = client.post(
        "/api/demo/extract",
        data={"file": [_file("a.png"), _file("b.png")]},
        content_type="multipart/form-data",
    )
    assert r.status_code == 400
    assert r.get_json()["code"] == "DEMO_SINGLE_FILE"


def test_unsupported_file_type_is_refused(client, app, monkeypatch):
    _stub_extract(monkeypatch)
    r = _post(client, file=_file("notes.txt", b"hello"))
    assert r.status_code == 415


def test_demo_can_be_switched_off(client, app, monkeypatch):
    monkeypatch.setitem(app.config, "DEMO_ENABLED", False)
    _stub_extract(monkeypatch)
    r = _post(client)
    assert r.status_code == 403
    assert r.get_json()["code"] == "DEMO_DISABLED"


def test_demo_result_is_not_attached_to_any_account(client, app, monkeypatch):
    """The demo must not create a real Extraction — nothing to leak into a
    stranger's history, and nobody's quota is spent."""
    _stub_extract(monkeypatch)
    _post(client)
    from models import Extraction
    with app.app_context():
        assert Extraction.query.count() == 0


# ─── Claiming ────────────────────────────────────────────────────────────────
def test_claim_turns_a_demo_into_a_real_extraction(client, app, monkeypatch):
    _stub_extract(monkeypatch)
    token = _post(client).get_json()["claimToken"]

    user = make_user(app)
    r = client.post("/api/demo/claim", json={"token": token}, headers=auth_header(app, user))
    assert r.status_code == 200
    body = r.get_json()
    assert body["claimed"] is True
    assert body["extraction"]["invoice"]["vendor"]["name"] == "Acme"
    # It counts toward the new account's monthly usage, like any extraction.
    assert body["usage"]["used"] == 1

    from models import Extraction
    with app.app_context():
        row = Extraction.query.filter_by(user_id=user["id"]).one()
        assert row.vendor_name == "Acme"
        assert row.status == "completed"
        assert json.loads(row.data)["total"] == 10.0


def test_claim_moves_the_original_file_across(client, app, monkeypatch):
    _stub_extract(monkeypatch)
    token = _post(client).get_json()["claimToken"]
    user = make_user(app)
    r = client.post("/api/demo/claim", json={"token": token}, headers=auth_header(app, user))
    files = r.get_json()["extraction"]["files"]
    assert [f["name"] for f in files] == ["invoice.png"]


def test_a_token_cannot_be_claimed_twice(client, app, monkeypatch):
    _stub_extract(monkeypatch)
    token = _post(client).get_json()["claimToken"]
    user = make_user(app)
    hdr = auth_header(app, user)
    assert client.post("/api/demo/claim", json={"token": token}, headers=hdr).get_json()["claimed"]
    second = client.post("/api/demo/claim", json={"token": token}, headers=hdr)
    assert second.status_code == 200
    assert second.get_json()["claimed"] is False


def test_claim_requires_a_session(client, app, monkeypatch):
    _stub_extract(monkeypatch)
    token = _post(client).get_json()["claimToken"]
    assert client.post("/api/demo/claim", json={"token": token}).status_code == 401


def test_unknown_token_is_reported_as_nothing_to_claim(client, app):
    """The browser fires claim on every sign-in while it holds a token, so a
    stale one must not surface as an error."""
    user = make_user(app)
    r = client.post("/api/demo/claim", json={"token": "nope"}, headers=auth_header(app, user))
    assert r.status_code == 200
    assert r.get_json() == {"claimed": False, "reason": "not_found"}


def test_expired_demos_are_purged(client, app, monkeypatch):
    """A result past the retention window is dropped, and its token stops working."""
    _stub_extract(monkeypatch)
    token = _post(client).get_json()["claimToken"]

    from datetime import datetime, timedelta
    from extensions import db
    from models import DemoExtraction
    with app.app_context():
        row = DemoExtraction.query.one()
        row.created_at = datetime.utcnow() - timedelta(hours=48)
        db.session.commit()

    # Any later demo request triggers the opportunistic purge. This IP is already
    # at its cap, so the 402 is expected — the purge runs first either way.
    _post(client)
    with app.app_context():
        assert DemoExtraction.query.count() == 0

    user = make_user(app)
    r = client.post("/api/demo/claim", json={"token": token}, headers=auth_header(app, user))
    assert r.get_json()["claimed"] is False


def test_per_ip_cap_survives_purging(client, app, monkeypatch):
    """Purging stored results must not hand an IP a fresh free extraction."""
    _stub_extract(monkeypatch)
    _post(client)
    from extensions import db
    from models import DemoExtraction
    with app.app_context():
        DemoExtraction.query.delete()
        db.session.commit()
    assert _post(client).status_code == 402
