"""Plan-capability gating + usage limits on /api/extract."""
import io

from tests.conftest import make_user, auth_header


def _file(name="invoice.png", content=b"\x89PNG\r\n\x1a\nfake"):
    return (io.BytesIO(content), name)


FAKE_INVOICE = {
    "vendor": {"name": "Acme", "address": None, "email": None},
    "invoice_number": "INV-1", "invoice_date": None, "due_date": None,
    "currency": "USD", "payment_terms": None, "line_items": [],
    "subtotal": None, "tax": None, "total": 10.0,
    "confidence": {k: 1.0 for k in (
        "vendor", "invoice_number", "invoice_date", "due_date", "currency",
        "payment_terms", "line_items", "subtotal", "tax", "total")},
}


def _stub_extract(monkeypatch):
    import routes.extract_routes as er
    monkeypatch.setattr(er, "extract_invoice", lambda pages: FAKE_INVOICE)


def test_batch_blocked_on_free(client, app, monkeypatch):
    _stub_extract(monkeypatch)
    user = make_user(app, plan="free")
    r = client.post(
        "/api/extract",
        data={"file": _file(), "mode": "batch"},
        headers=auth_header(app, user),
        content_type="multipart/form-data",
    )
    assert r.status_code == 402
    body = r.get_json()
    assert body["code"] == "UPGRADE_REQUIRED" and body["capability"] == "batch"


def test_batch_allowed_on_starter(client, app, monkeypatch):
    _stub_extract(monkeypatch)
    user = make_user(app, email="s@example.com", plan="starter")
    r = client.post(
        "/api/extract",
        data={"file": _file(), "mode": "batch"},
        headers=auth_header(app, user),
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    assert r.get_json()["invoice"]["vendor"]["name"] == "Acme"


def test_multipage_blocked_on_free(client, app, monkeypatch):
    _stub_extract(monkeypatch)
    user = make_user(app, plan="free")
    r = client.post(
        "/api/extract",
        data={"file": [_file("a.png"), _file("b.png")]},
        headers=auth_header(app, user),
        content_type="multipart/form-data",
    )
    assert r.status_code == 402
    assert r.get_json()["capability"] == "multiPage"


def test_usage_limit_reached_returns_402(client, app, monkeypatch):
    _stub_extract(monkeypatch)
    user = make_user(app, plan="free")
    # Free limit is 5 — pre-seed 5 completed extractions this month.
    from extensions import db
    from models import Extraction
    with app.app_context():
        for i in range(5):
            db.session.add(Extraction(
                user_id=user["id"], file_name=f"f{i}", file_type="image/png",
                file_size=10, data="{}", status="completed",
            ))
        db.session.commit()

    r = client.post(
        "/api/extract",
        data={"file": _file()},
        headers=auth_header(app, user),
        content_type="multipart/form-data",
    )
    assert r.status_code == 402
    assert r.get_json()["code"] == "LIMIT_REACHED"
