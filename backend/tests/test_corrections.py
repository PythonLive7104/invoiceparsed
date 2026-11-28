"""Audit trail for manual corrections.

Two reasons this has to be right. The obvious one: a financial document's
history must be defensible, and the original value can never be destroyed. The
less obvious one: these rows are the only honest record of where extraction
goes wrong, so a trail full of phantom edits is worse than none - it would
poison the signal used to improve the prompt.
"""
import io

import pytest

from invoice_schema import normalize
from tests.conftest import auth_header, make_user

INVOICE = {
    "vendor": {"name": "Acme Ltd", "email": "ar@acme.example", "tax_id": "TIN-1"},
    "customer": {"name": "Buyer Co"},
    "invoice_number": "INV-1",
    "invoice_date": "2026-10-15",
    "due_date": "2026-11-14",
    "currency": "USD",
    "line_items": [
        {"description": "Design", "quantity": 2, "unit_price": 100, "amount": 200},
        {"description": "Hosting", "quantity": 1, "unit_price": 20, "amount": 20},
    ],
    "subtotal": 220, "tax": 22, "tax_percentage": 10, "total": 242,
    "confidence": {},
}


@pytest.fixture
def document(client, app, monkeypatch):
    import routes.extract_routes as er
    monkeypatch.setattr(
        "openai_service.extract_document", lambda pages, doc_type="invoice": normalize(INVOICE)
    )
    user = make_user(app, email="audit@example.com", plan="pro")
    headers = auth_header(app, user)
    r = client.post(
        "/api/extract",
        data={"file": (io.BytesIO(b"fake"), "inv.pdf")},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert r.status_code == 200, r.get_json()
    return r.get_json(), headers


def _patch(client, body, headers, invoice, **extra):
    r = client.patch(
        f"/api/extractions/{body['id']}",
        json={"invoice": invoice, **extra},
        headers=headers,
    )
    assert r.status_code == 200, r.get_json()
    return r.get_json()


# ─── Recording ───────────────────────────────────────────────────────────────
def test_a_changed_field_is_recorded_with_both_values(client, document):
    body, headers = document
    edited = dict(body["invoice"], invoice_number="INV-CORRECTED")
    result = _patch(client, body, headers, edited)

    trail = result["corrections"]
    assert len(trail) == 1
    entry = trail[0]
    assert entry["field"] == "invoice_number"
    assert entry["from"] == "INV-1"
    assert entry["to"] == "INV-CORRECTED"
    assert entry["by"]      # who
    assert entry["at"]      # when


def test_the_original_value_survives_further_edits(client, document):
    """The point of the trail: what the document said before anyone touched it
    must remain recoverable."""
    body, headers = document
    first = _patch(client, body, headers, dict(body["invoice"], total="300.00"))
    second = _patch(client, body, headers, dict(first["invoice"], total="400.00"))

    totals = [c for c in second["corrections"] if c["field"] == "total"]
    assert len(totals) == 2
    assert {"242.00"} <= {c["from"] for c in totals}


def test_a_line_item_change_names_the_exact_cell(client, document):
    """'line_items changed' would be useless; the path identifies one cell."""
    body, headers = document
    edited = dict(body["invoice"])
    edited["line_items"] = [dict(item) for item in edited["line_items"]]
    edited["line_items"][1]["unit_price"] = "25.00"

    trail = _patch(client, body, headers, edited)["corrections"]
    paths = {c["field"] for c in trail}
    assert "line_items.1.unit_price" in paths


def test_nested_party_fields_are_recorded(client, document):
    body, headers = document
    edited = dict(body["invoice"])
    edited["vendor"] = {**edited["vendor"], "tax_id": "TIN-CHANGED"}
    trail = _patch(client, body, headers, edited)["corrections"]
    assert any(c["field"] == "vendor.tax_id" for c in trail)


def test_several_changes_in_one_save_are_all_recorded(client, document):
    body, headers = document
    edited = dict(body["invoice"], invoice_number="X-1", currency="EUR")
    trail = _patch(client, body, headers, edited)["corrections"]
    assert {c["field"] for c in trail} == {"invoice_number", "currency"}


def test_a_reason_is_stored_when_supplied(client, document):
    body, headers = document
    edited = dict(body["invoice"], total="250.00")
    trail = _patch(client, body, headers, edited,
                   reason="Supplier confirmed by phone")["corrections"]
    assert trail[0]["reason"] == "Supplier confirmed by phone"


# ─── Not recording noise ─────────────────────────────────────────────────────
def test_saving_without_changing_anything_records_nothing(client, document):
    """Re-saving an untouched form must not manufacture a trail."""
    body, headers = document
    assert _patch(client, body, headers, body["invoice"])["corrections"] == []


def test_a_reformatted_number_is_not_an_edit(client, document):
    """100 and '100.00' are the same value written differently. Both sides are
    normalized before diffing, so this is not reported as a correction."""
    body, headers = document
    edited = dict(body["invoice"], total=242)   # was the string "242.00"
    assert _patch(client, body, headers, edited)["corrections"] == []


def test_blank_and_null_count_as_the_same_absence(client, document):
    """Otherwise every empty field in the form produces a phantom edit."""
    body, headers = document
    edited = dict(body["invoice"])
    edited["payment_terms"] = ""        # was null
    assert _patch(client, body, headers, edited)["corrections"] == []


def test_confidence_scores_are_never_audited(client, document):
    """They are the model's own scoring, not user data."""
    body, headers = document
    edited = dict(body["invoice"], invoice_number="X-9")
    trail = _patch(client, body, headers, edited)["corrections"]
    assert all(not c["field"].startswith("confidence") for c in trail)


# ─── Exposure and isolation ──────────────────────────────────────────────────
def test_the_trail_is_returned_when_the_document_is_reloaded(client, document):
    body, headers = document
    _patch(client, body, headers, dict(body["invoice"], total="999.00"))
    reloaded = client.get(f"/api/extractions/{body['id']}", headers=headers).get_json()
    assert any(c["field"] == "total" for c in reloaded["corrections"])


def test_newest_corrections_come_first(client, document):
    body, headers = document
    first = _patch(client, body, headers, dict(body["invoice"], currency="EUR"))
    _patch(client, body, headers, dict(first["invoice"], invoice_number="LATEST"))
    reloaded = client.get(f"/api/extractions/{body['id']}", headers=headers).get_json()
    assert reloaded["corrections"][0]["field"] == "invoice_number"


def test_another_organization_cannot_see_the_trail(client, app, document):
    body, headers = document
    _patch(client, body, headers, dict(body["invoice"], total="500.00"))

    outsider = make_user(app, email="outsider@example.com", plan="pro")
    r = client.get(f"/api/extractions/{body['id']}", headers=auth_header(app, outsider))
    assert r.status_code == 404


def test_editing_marks_the_document_reviewed(client, document):
    """Someone changing a field has, by definition, looked at it."""
    body, headers = document
    _patch(client, body, headers, dict(body["invoice"], total="260.00"))
    rows = client.get("/api/extractions", headers=headers).get_json()["extractions"]
    assert rows[0]["reviewed"] is True
