"""End-to-end exactness: extraction -> storage -> API -> export.

test_money.py covers the money module in isolation. These tests prove the
Decimal survives every hop, because the places money historically turns back
into a float are the boundaries: the ORM column, the JSON response, the stored
payload and the spreadsheet exporters.
"""
import io
import json
from decimal import Decimal

from tests.conftest import auth_header, make_user

# Line items chosen so a float pipeline visibly disagrees with the stated total:
# 0.1 * 3 is 0.30000000000000004 in binary floating point.
DRIFTY_INVOICE = {
    "vendor": {"name": "Acme", "address": None, "email": None},
    "invoice_number": "INV-DEC-1",
    "invoice_date": "2026-01-15",
    "due_date": None,
    "currency": "USD",
    "payment_terms": None,
    "line_items": [
        {"description": "a", "quantity": 1, "unit_price": 0.1, "amount": 0.1},
        {"description": "b", "quantity": 1, "unit_price": 0.1, "amount": 0.1},
        {"description": "c", "quantity": 1, "unit_price": 0.1, "amount": 0.1},
    ],
    "subtotal": 0.3,
    "tax": 0.0,
    "total": 0.3,
    "confidence": {k: 1.0 for k in (
        "vendor", "invoice_number", "invoice_date", "due_date", "currency",
        "payment_terms", "line_items", "subtotal", "tax", "total")},
}


def _extract(client, app, monkeypatch, payload=DRIFTY_INVOICE, email="dec@example.com"):
    """Run an extraction with the OpenAI call stubbed out.

    The stub returns `normalize(payload)`, not `payload`: the real
    `extract_document` normalizes before returning, so a stub handing back raw
    floats would skip the very conversion these tests exist to verify.
    """
    import routes.extract_routes as er
    from invoice_schema import normalize

    monkeypatch.setattr(
        "openai_service.extract_document", lambda pages, doc_type="invoice": normalize(payload)
    )
    user = make_user(app, email=email, plan="pro")
    headers = auth_header(app, user)
    r = client.post(
        "/api/extract",
        data={"file": (io.BytesIO(b"fake-png"), "inv.png")},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert r.status_code == 200, r.get_json()
    return r.get_json(), headers


def test_api_returns_money_as_exact_decimal_strings(client, app, monkeypatch):
    body, _ = _extract(client, app, monkeypatch)
    inv = body["invoice"]

    assert inv["total"] == "0.30"
    assert inv["subtotal"] == "0.30"
    assert inv["tax"] == "0.00"
    assert [li["amount"] for li in inv["line_items"]] == ["0.10", "0.10", "0.10"]

    # Strings, not JSON numbers: a number would be read back as a double.
    assert isinstance(inv["total"], str)


def test_line_items_sum_exactly_to_the_stated_total(client, app, monkeypatch):
    """The whole point: the sum agrees with the document, with no tolerance."""
    body, _ = _extract(client, app, monkeypatch)
    inv = body["invoice"]
    summed = sum(Decimal(li["amount"]) for li in inv["line_items"])
    assert summed == Decimal(inv["total"])


def test_stored_payload_matches_the_api_response(client, app, monkeypatch):
    """Extraction.data is serialized separately from the Flask response, so it
    has its own chance to turn a Decimal into a float."""
    body, _ = _extract(client, app, monkeypatch)
    from models import Extraction

    with app.app_context():
        row = Extraction.query.filter_by(id=body["id"]).first()
        stored = json.loads(row.data)
        assert stored["total"] == "0.30"
        assert stored["line_items"][0]["amount"] == "0.10"
        # The denormalized column is a real Decimal, not a float.
        assert row.total == Decimal("0.30")
        assert isinstance(row.total, Decimal)


def test_quantities_keep_four_places(client, app, monkeypatch):
    """A quantity is not money and must not be forced to 2 places."""
    payload = json.loads(json.dumps(DRIFTY_INVOICE))
    payload["line_items"][0]["quantity"] = 3.5
    payload["line_items"][0]["unit_price"] = 0.0825
    body, _ = _extract(client, app, monkeypatch, payload, email="qty@example.com")
    li = body["invoice"]["line_items"][0]
    assert li["quantity"] == "3.5000"
    assert li["unit_price"] == "0.0825"


def test_user_edits_are_parsed_exactly(client, app, monkeypatch):
    """A PATCH carrying money as a string must round-trip without a float."""
    body, headers = _extract(client, app, monkeypatch, email="edit@example.com")
    edited = dict(body["invoice"])
    edited["total"] = "1234567.89"
    edited["tax"] = "0.07"

    r = client.patch(f"/api/extractions/{body['id']}", json={"invoice": edited}, headers=headers)
    assert r.status_code == 200
    inv = r.get_json()["invoice"]
    assert inv["total"] == "1234567.89"
    assert inv["tax"] == "0.07"


def test_messy_user_input_is_parsed_not_rejected(client, app, monkeypatch):
    """People paste "$1,234.56" into a money field."""
    body, headers = _extract(client, app, monkeypatch, email="messy@example.com")
    edited = dict(body["invoice"])
    edited["total"] = "$1,234.56"

    r = client.patch(f"/api/extractions/{body['id']}", json={"invoice": edited}, headers=headers)
    assert r.status_code == 200
    assert r.get_json()["invoice"]["total"] == "1234.56"


# ─── Exporters ───────────────────────────────────────────────────────────────
def test_csv_export_writes_exact_amounts(client, app, monkeypatch):
    body, headers = _extract(client, app, monkeypatch, email="csv@example.com")
    r = client.get(f"/api/extractions/{body['id']}/csv", headers=headers)
    assert r.status_code == 200
    text = r.get_data(as_text=True)
    # Exact, and with no float artefacts such as 0.30000000000000004.
    assert "0.30" in text
    assert "0.10" in text
    assert "0000000" not in text


def test_xlsx_export_succeeds_with_decimals(client, app, monkeypatch):
    """openpyxl accepts Decimal, but only if nothing converted it to str first."""
    body, headers = _extract(client, app, monkeypatch, email="xlsx@example.com")
    r = client.get(f"/api/extractions/{body['id']}/xlsx", headers=headers)
    assert r.status_code == 200
    assert r.get_data()[:2] == b"PK"  # a real xlsx is a zip

    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(r.get_data()))
    rows = list(wb.active.iter_rows(values_only=True))
    headers, first = rows[0], rows[1]
    cells = dict(zip(headers, first, strict=False))

    # Amounts must arrive as numbers, not text. If they land as strings, Excel
    # shows them left-aligned and SUM() over the column returns 0 - the export
    # looks right and is useless. (The xlsx format stores numbers as doubles,
    # so reading back a float here is the format's own representation, not our
    # pipeline reintroducing one.)
    for column in ("Amount", "Total", "Subtotal"):
        assert isinstance(cells[column], int | float | Decimal), (
            f"{column} came through as {type(cells[column]).__name__}: {cells[column]!r}"
        )
    assert float(cells["Amount"]) == 0.10
    assert float(cells["Total"]) == 0.30


def test_webhook_payload_money_matches_the_api(client, app, monkeypatch):
    """Webhook bodies are serialized outside Flask, so they can disagree."""
    import webhooks

    captured = {}

    def fake_post(url, content=None, headers=None, **kwargs):
        captured["body"] = content

        class R:
            status_code = 200
        return R()

    monkeypatch.setattr(webhooks.httpx, "post", fake_post)
    monkeypatch.setattr(webhooks, "url_is_safe", lambda url: True)

    from extensions import db
    from models import Webhook

    body, _ = _extract(client, app, monkeypatch, email="hook@example.com")
    with app.app_context():
        from models import Extraction
        row = Extraction.query.filter_by(id=body["id"]).first()
        hook = Webhook(organization_id=row.organization_id, user_id=row.user_id,
                       url="https://example.com/hook", secret="s")
        db.session.add(hook)
        db.session.commit()
        webhooks.deliver(hook, "extraction.completed", json.loads(row.data),
                         sleep=lambda _s: None, max_attempts=1)

    sent = json.loads(captured["body"].decode("utf-8"))
    assert sent["data"]["total"] == "0.30"
