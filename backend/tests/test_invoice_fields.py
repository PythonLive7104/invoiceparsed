"""Full invoice field coverage, end to end.

The extraction schema grew from 10 fields to 19, plus customer details, vendor
bank details and richer line items. These tests follow the whole path - model
output, normalize, database, API, CSV - because a field that is extracted but
lost on the way to the user is invisible work.
"""
import csv
import io
from decimal import Decimal

import pytest

from invoice_schema import CONFIDENCE_FIELDS, INVOICE_JSON_SCHEMA, normalize
from tests.conftest import auth_header, make_user

FULL_INVOICE = {
    "vendor": {
        "name": "Acme Supplies Ltd", "address": "1 Trade St, Lagos",
        "email": "ar@acme.example", "phone": "+234 800 000 0000",
        "tax_id": "TIN-12345", "registration_number": "RC-98765",
        "bank_details": {
            "bank_name": "First Bank", "account_name": "Acme Supplies Ltd",
            "account_number": "0123456789", "iban": None, "swift": "FBNINGLA",
            "sort_code": None,
        },
    },
    "customer": {
        "name": "Buyer Industries", "address": "9 Market Rd",
        "email": "ap@buyer.example", "phone": None, "tax_id": "TIN-55555",
    },
    "invoice_number": "INV-2026-001",
    "invoice_type": "invoice",
    "purchase_order_reference": "PO-4471",
    "invoice_date": "2026-10-15",
    "due_date": "2026-11-14",
    "currency": "NGN",
    "payment_terms": "Net 30",
    "line_items": [
        {"description": "Copier paper, A4", "product_name": "PAP-A4",
         "quantity": 10, "unit_price": "2500.00", "discount": "500.00",
         "tax_rate": 7.5, "amount": "24500.00"},
        {"description": "Delivery", "product_name": None, "quantity": 1,
         "unit_price": "1500.00", "discount": None, "tax_rate": 7.5,
         "amount": "1500.00"},
    ],
    "subtotal": "26000.00",
    "discount": "500.00",
    "tax": "1950.00",
    "tax_percentage": 7.5,
    "shipping": "1500.00",
    "other_charges": "0.00",
    "total": "28950.00",
    "amount_paid": "10000.00",
    "balance_due": "18950.00",
    "confidence": {f: 0.9 for f in CONFIDENCE_FIELDS},
}


# ─── Schema ──────────────────────────────────────────────────────────────────
def test_schema_covers_the_specified_field_set():
    """Every field the brief asks for must be in the schema, or the model is
    simply never asked for it."""
    props = INVOICE_JSON_SCHEMA["properties"]
    assert {
        "vendor", "customer", "invoice_number", "invoice_type",
        "purchase_order_reference", "invoice_date", "due_date", "currency",
        "subtotal", "discount", "tax", "tax_percentage", "shipping",
        "other_charges", "total", "amount_paid", "balance_due", "line_items",
    } <= set(props)

    vendor = props["vendor"]["properties"]
    assert {"name", "address", "email", "phone", "tax_id",
            "registration_number", "bank_details"} <= set(vendor)

    item = props["line_items"]["items"]["properties"]
    assert {"description", "product_name", "quantity", "unit_price",
            "discount", "tax_rate", "amount"} <= set(item)


def test_every_field_has_a_confidence_score():
    props = set(INVOICE_JSON_SCHEMA["properties"]) - {"confidence"}
    assert props == set(CONFIDENCE_FIELDS)


def test_schema_satisfies_openai_strict_mode():
    """Strict mode requires additionalProperties:false and every property listed
    in `required`. A violation is rejected at request time, so extraction fails
    outright rather than degrading."""
    def audit(node, path="root"):
        if not isinstance(node, dict):
            return
        types = node.get("type")
        types = types if isinstance(types, list) else [types]
        if "object" in types:
            assert node.get("additionalProperties") is False, path
            assert set(node.get("properties", {})) == set(node.get("required", [])), path
        for key, child in (node.get("properties") or {}).items():
            audit(child, f"{path}.{key}")
        if "items" in node:
            audit(node["items"], path + "[]")

    audit(INVOICE_JSON_SCHEMA)


# ─── Normalization ───────────────────────────────────────────────────────────
def test_normalize_preserves_every_field():
    out = normalize(FULL_INVOICE)
    assert out["purchase_order_reference"] == "PO-4471"
    assert out["customer"]["name"] == "Buyer Industries"
    assert out["vendor"]["registration_number"] == "RC-98765"
    assert out["vendor"]["bank_details"]["swift"] == "FBNINGLA"
    assert out["balance_due"] == Decimal("18950.00")
    assert out["line_items"][0]["product_name"] == "PAP-A4"
    assert out["line_items"][0]["discount"] == Decimal("500.00")
    assert out["line_items"][0]["tax_rate"] == Decimal("7.5000")


@pytest.mark.parametrize("raw,expected", [
    ("credit note", "credit_note"),
    ("Credit-Note", "credit_note"),
    ("PROFORMA", "proforma"),
    ("debit_note", "debit_note"),
    (None, "invoice"),
    ("something else", "invoice"),
])
def test_invoice_type_is_normalized(raw, expected):
    """A credit note reduces what is owed; mistaking one for a charge would
    overstate a payable."""
    assert normalize({"invoice_type": raw})["invoice_type"] == expected


def test_empty_bank_block_becomes_absent():
    """So the UI hides the section instead of showing a card full of dashes."""
    out = normalize({"vendor": {"name": "X", "bank_details": {
        "bank_name": None, "account_name": None, "account_number": None,
        "iban": None, "swift": None, "sort_code": None}}})
    assert out["vendor"]["bank_details"] is None


def test_missing_input_still_yields_every_key():
    """Payloads stored before this change lack the new fields; reading one back
    must not raise."""
    out = normalize({"vendor": {"name": "Old"}, "total": "5.00"})
    for key in CONFIDENCE_FIELDS:
        assert key in out
    assert out["customer"]["name"] is None
    assert out["purchase_order_reference"] is None


# ─── End to end ──────────────────────────────────────────────────────────────
def _extract(client, app, monkeypatch):
    import routes.extract_routes as er
    monkeypatch.setattr(
        "openai_service.extract_document", lambda pages, doc_type="invoice": normalize(FULL_INVOICE)
    )
    user = make_user(app, email="fields@example.com", plan="pro")
    headers = auth_header(app, user)
    r = client.post(
        "/api/extract",
        data={"file": (io.BytesIO(b"fake-png"), "inv.png")},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert r.status_code == 200, r.get_json()
    return r.get_json(), headers


def test_api_returns_the_new_fields(client, app, monkeypatch):
    body, _ = _extract(client, app, monkeypatch)
    inv = body["invoice"]
    assert inv["purchase_order_reference"] == "PO-4471"
    assert inv["customer"]["tax_id"] == "TIN-55555"
    assert inv["vendor"]["bank_details"]["account_number"] == "0123456789"
    # Money is still exact decimal strings on the wire.
    assert inv["balance_due"] == "18950.00"
    assert inv["amount_paid"] == "10000.00"


def test_new_fields_survive_a_reload_from_storage(client, app, monkeypatch):
    """The stored payload is re-normalized on read, so the extra fields have to
    round-trip through the database."""
    body, headers = _extract(client, app, monkeypatch)
    reloaded = client.get(f"/api/extractions/{body['id']}", headers=headers).get_json()
    assert reloaded["invoice"]["purchase_order_reference"] == "PO-4471"
    assert reloaded["invoice"]["customer"]["name"] == "Buyer Industries"


def test_csv_export_includes_the_new_fields(client, app, monkeypatch):
    body, headers = _extract(client, app, monkeypatch)
    text = client.get(
        f"/api/extractions/{body['id']}/csv", headers=headers
    ).get_data(as_text=True)
    rows = list(csv.reader(io.StringIO(text)))
    cells = dict(zip(rows[0], rows[1], strict=False))
    assert cells["PO Reference"] == "PO-4471"
    assert cells["Customer"] == "Buyer Industries"
    assert cells["Vendor Tax ID"] == "TIN-12345"
    assert cells["Balance Due"] == "18950.00"
    assert cells["Product"] == "PAP-A4"


def test_invoice_level_totals_appear_once(client, app, monkeypatch):
    """Repeating them on every line would make a SUM over the column multiply
    the invoice by its line count."""
    body, headers = _extract(client, app, monkeypatch)
    text = client.get(
        f"/api/extractions/{body['id']}/csv", headers=headers
    ).get_data(as_text=True)
    rows = list(csv.reader(io.StringIO(text)))
    header = rows[0]
    totals = [r[header.index("Total")] for r in rows[1:]]
    assert totals[0] == "28950.00"
    assert all(t == "" for t in totals[1:])


def test_the_api_includes_a_validation_verdict(client, app, monkeypatch):
    """Validation has to reach the client, or it is invisible work."""
    body, headers = _extract(client, app, monkeypatch)
    verdict = body["validation"]
    assert verdict["status"] in (
        "valid", "valid_with_warnings", "requires_review", "invalid",
    )
    assert "issues" in verdict and "counts" in verdict


def test_validation_is_recomputed_after_an_edit(client, app, monkeypatch):
    """It is derived on read, not stored, so correcting a figure must clear the
    warning rather than leave a stale verdict behind."""
    body, headers = _extract(client, app, monkeypatch)

    broken = dict(body["invoice"], total="999999.00")
    r = client.patch(f"/api/extractions/{body['id']}",
                     json={"invoice": broken}, headers=headers)
    assert r.status_code == 200
    codes = {i["code"] for i in r.get_json()["validation"]["issues"]}
    assert "total_mismatch" in codes

    fixed = dict(body["invoice"])
    r = client.patch(f"/api/extractions/{body['id']}",
                     json={"invoice": fixed}, headers=headers)
    codes = {i["code"] for i in r.get_json()["validation"]["issues"]}
    assert "total_mismatch" not in codes
