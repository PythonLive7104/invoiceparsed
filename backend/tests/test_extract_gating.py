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
    monkeypatch.setattr(er, "extract_document", lambda pages, doc_type="invoice": FAKE_INVOICE)


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


FAKE_RECEIPT = {
    "merchant": {"name": "Cafe Roma", "address": "5 High St"},
    "receipt_date": "2026-02-01", "receipt_number": "R-9", "payment_method": "Visa ****1234",
    "category": "Meals", "currency": "USD",
    "line_items": [{"description": "Latte", "quantity": 2, "unit_price": 4, "amount": 8}],
    "subtotal": 8, "tax": 0.8, "tip": 1.5, "total": 10.3,
    "confidence": {k: 1.0 for k in (
        "merchant", "receipt_date", "receipt_number", "payment_method", "category",
        "currency", "line_items", "subtotal", "tax", "tip", "total")},
}


def test_receipt_extraction_stores_doc_type_and_headline(client, app, monkeypatch):
    import routes.extract_routes as er
    monkeypatch.setattr(er, "extract_document", lambda pages, doc_type="invoice": FAKE_RECEIPT)
    user = make_user(app, plan="free")
    r = client.post(
        "/api/extract",
        data={"file": _file("receipt.jpg"), "doc_type": "receipt"},
        headers=auth_header(app, user),
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["docType"] == "receipt"
    assert body["invoice"]["merchant"]["name"] == "Cafe Roma"

    # Headline columns mapped from receipt fields (merchant→vendor, date, total).
    from models import Extraction
    with app.app_context():
        row = Extraction.query.get(body["id"])
        assert row.doc_type == "receipt"
        assert row.vendor_name == "Cafe Roma"
        assert row.invoice_date == "2026-02-01"
        assert row.total == 10.3


def test_receipt_patch_uses_receipt_schema(client, app, monkeypatch):
    import routes.extract_routes as er
    monkeypatch.setattr(er, "extract_document", lambda pages, doc_type="invoice": FAKE_RECEIPT)
    user = make_user(app, plan="free")
    created = client.post(
        "/api/extract",
        data={"file": _file("receipt.jpg"), "doc_type": "receipt"},
        headers=auth_header(app, user),
        content_type="multipart/form-data",
    ).get_json()

    edited = dict(FAKE_RECEIPT)
    edited["merchant"] = {"name": "Edited Cafe", "address": None}
    edited["tip"] = 3.5
    r = client.patch(f"/api/extractions/{created['id']}", json={"invoice": edited},
                     headers=auth_header(app, user))
    assert r.status_code == 200
    body = r.get_json()
    # Receipt-shaped fields survive the PATCH (proves receipt normalize was used).
    assert body["invoice"]["merchant"]["name"] == "Edited Cafe"
    assert body["invoice"]["tip"] == 3.5
    assert body["docType"] == "receipt"


FAKE_STATEMENT = {
    "account_holder": "Solomon O", "account_number": "9152608026", "bank_name": "OPay",
    "currency": "NGN", "period_start": "2026-05-08", "period_end": "2026-05-25",
    "opening_balance": 0.0, "closing_balance": 0.0, "total_debit": 1349881.0, "total_credit": 1349881.0,
    "transactions": [
        {"date": "2026-05-08", "description": "Airtime", "debit": 84.0, "credit": None, "balance": 0.0, "reference": "A1"},
        {"date": "2026-05-08", "description": "Wallet Withdrawal", "debit": None, "credit": 84.0, "balance": 84.0, "reference": "A2"},
    ],
    "confidence": {k: 1.0 for k in (
        "account_holder", "account_number", "bank_name", "currency", "period_start",
        "period_end", "opening_balance", "closing_balance", "total_debit", "total_credit", "transactions")},
}


def test_statement_extraction_maps_headline_and_csv(client, app, monkeypatch):
    import routes.extract_routes as er
    monkeypatch.setattr(er, "extract_document", lambda pages, doc_type="invoice": FAKE_STATEMENT)
    user = make_user(app, plan="free")
    r = client.post(
        "/api/extract",
        data={"file": _file("statement.png"), "doc_type": "statement"},
        headers=auth_header(app, user),
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["docType"] == "statement"
    assert len(body["invoice"]["transactions"]) == 2

    from models import Extraction
    with app.app_context():
        row = Extraction.query.get(body["id"])
        assert row.doc_type == "statement"
        assert row.vendor_name == "Solomon O"          # account holder → vendor headline
        assert row.invoice_date == "2026-05-08"          # period_start → date headline
        assert row.currency == "NGN"

    # CSV export uses the statement (transactions) format.
    csv_resp = client.get(f"/api/extractions/{body['id']}/csv", headers=auth_header(app, user))
    assert csv_resp.status_code == 200
    text = csv_resp.get_data(as_text=True)
    assert "Date,Description,Debit,Credit,Balance,Reference" in text
    assert "Airtime" in text


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
