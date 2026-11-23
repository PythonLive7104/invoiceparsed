"""Supplier management and matching.

Attaching an invoice to the WRONG supplier is worse than leaving it
unattached: the error is invisible, the totals simply come out wrong and
nothing looks broken. So these tests push as hard on "does not match" as on
"matches".

Bank details get their own section. They are the highest-value target in the
dataset — invoice-redirection fraud works by changing them.
"""
import io

import pytest

from extensions import db
from invoice_schema import normalize
from models import Supplier
from tests.conftest import auth_header, join_org, make_org, make_user, org_header

VENDOR = {
    "name": "Acme Supplies Ltd", "email": "ar@acme.example",
    "address": "1 Trade St", "phone": "+234 800 1", "tax_id": "TIN-1",
    "registration_number": "RC-9",
    "bank_details": {
        "bank_name": "First Bank", "account_name": "Acme Supplies Ltd",
        "account_number": "0123456789", "iban": None, "swift": "FBNINGLA",
        "sort_code": None,
    },
}


def _invoice(**overrides):
    base = {
        "vendor": dict(VENDOR), "invoice_number": "INV-1",
        "invoice_date": "2026-10-15", "currency": "USD",
        "line_items": [{"description": "x", "quantity": 1, "unit_price": 100,
                        "amount": 100}],
        "subtotal": 100, "tax": 0, "tax_percentage": 0, "total": 100,
        "confidence": {},
    }
    base.update(overrides)
    return normalize(base)


@pytest.fixture
def account(app):
    user = make_user(app, email="sup@example.com", plan="pro")
    return user, auth_header(app, user)


def _upload(client, app, monkeypatch, headers, payload=None, content=b"x"):
    import routes.extract_routes as er
    monkeypatch.setattr(
        er, "extract_document",
        lambda pages, doc_type="invoice": payload or _invoice(),
    )
    r = client.post(
        "/api/extract",
        data={"file": (io.BytesIO(content), "inv.pdf")},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def _suppliers(client, headers, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    r = client.get(f"/api/suppliers?{query}", headers=headers)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


# ─── Automatic creation and matching ─────────────────────────────────────────
def test_an_invoice_creates_its_supplier(client, app, monkeypatch, account):
    _user, headers = account
    _upload(client, app, monkeypatch, headers)

    rows = _suppliers(client, headers)["suppliers"]
    assert len(rows) == 1
    assert rows[0]["name"] == "Acme Supplies Ltd"
    assert rows[0]["taxId"] == "TIN-1"
    assert rows[0]["invoiceCount"] == 1


def test_a_second_invoice_reuses_the_same_supplier(client, app, monkeypatch, account):
    _user, headers = account
    _upload(client, app, monkeypatch, headers, content=b"a")
    _upload(client, app, monkeypatch, headers,
            payload=_invoice(invoice_number="INV-2"), content=b"b")

    rows = _suppliers(client, headers)["suppliers"]
    assert len(rows) == 1
    assert rows[0]["invoiceCount"] == 2


def test_name_variations_match_the_same_supplier(client, app, monkeypatch, account):
    """'Acme Supplies Ltd.' and 'acme supplies limited' are one business."""
    _user, headers = account
    _upload(client, app, monkeypatch, headers, content=b"a")
    _upload(client, app, monkeypatch, headers, content=b"b", payload=_invoice(
        vendor={**VENDOR, "name": "acme supplies limited"}, invoice_number="INV-2",
    ))
    assert len(_suppliers(client, headers)["suppliers"]) == 1


def test_tax_id_matches_even_when_the_name_was_read_differently(
    client, app, monkeypatch, account
):
    """A tax ID is government-issued and exact; two businesses cannot share
    one. It outranks a name the scanner may have mangled."""
    _user, headers = account
    _upload(client, app, monkeypatch, headers, content=b"a")
    _upload(client, app, monkeypatch, headers, content=b"b", payload=_invoice(
        vendor={"name": "ACNE Supplles", "tax_id": "TIN-1"}, invoice_number="INV-2",
    ))
    assert len(_suppliers(client, headers)["suppliers"]) == 1


def test_a_genuinely_different_supplier_gets_its_own_record(
    client, app, monkeypatch, account
):
    _user, headers = account
    _upload(client, app, monkeypatch, headers, content=b"a")
    _upload(client, app, monkeypatch, headers, content=b"b", payload=_invoice(
        vendor={"name": "Zenith Trading", "tax_id": "TIN-2"}, invoice_number="INV-2",
    ))
    assert len(_suppliers(client, headers)["suppliers"]) == 2


def test_an_invoice_with_no_supplier_name_creates_nothing(
    client, app, monkeypatch, account
):
    """A nameless supplier record would match every later nameless invoice,
    silently lumping unrelated documents together."""
    _user, headers = account
    body = _upload(client, app, monkeypatch, headers,
                   payload=_invoice(vendor={"name": None}))
    assert _suppliers(client, headers)["suppliers"] == []
    # ...and the document still processed.
    assert body["id"]


def test_receipts_do_not_create_suppliers(client, app, monkeypatch, account):
    """Supplier records are an accounts-payable concept; a coffee receipt is
    not a supplier relationship."""
    _user, headers = account
    import routes.extract_routes as er
    monkeypatch.setattr(er, "extract_document",
                        lambda pages, doc_type="invoice": _invoice())
    client.post(
        "/api/extract",
        data={"file": (io.BytesIO(b"r"), "r.jpg"), "doc_type": "receipt"},
        headers=headers, content_type="multipart/form-data",
    )
    assert _suppliers(client, headers)["suppliers"] == []


def test_blank_details_are_filled_in_from_a_later_invoice(
    client, app, monkeypatch, account
):
    _user, headers = account
    _upload(client, app, monkeypatch, headers, content=b"a", payload=_invoice(
        vendor={"name": "Acme Supplies Ltd"},
    ))
    _upload(client, app, monkeypatch, headers, content=b"b", payload=_invoice(
        vendor={"name": "Acme Supplies Ltd", "email": "later@acme.example"},
        invoice_number="INV-2",
    ))
    rows = _suppliers(client, headers)["suppliers"]
    assert rows[0]["email"] == "later@acme.example"


def test_an_existing_detail_is_never_overwritten_by_an_extraction(
    client, app, monkeypatch, account
):
    """A hand-corrected record outranks whatever the extractor read off the
    latest scan."""
    _user, headers = account
    _upload(client, app, monkeypatch, headers, content=b"a")
    supplier_id = _suppliers(client, headers)["suppliers"][0]["id"]
    client.patch(f"/api/suppliers/{supplier_id}",
                 json={"email": "corrected@acme.example"}, headers=headers)

    _upload(client, app, monkeypatch, headers, content=b"b",
            payload=_invoice(invoice_number="INV-2"))
    rows = _suppliers(client, headers)["suppliers"]
    assert rows[0]["email"] == "corrected@acme.example"


# ─── Manual management ───────────────────────────────────────────────────────
def test_a_supplier_can_be_created_by_hand(client, app, account):
    _user, headers = account
    r = client.post("/api/suppliers", json={
        "name": "Manual Co", "email": "hi@manual.example", "currency": "NGN",
    }, headers=headers)
    assert r.status_code == 201
    assert r.get_json()["supplier"]["name"] == "Manual Co"


def test_creating_a_supplier_that_already_exists_is_refused(client, app, account):
    """Two records for one business make 'how much do we owe them' unanswerable."""
    _user, headers = account
    client.post("/api/suppliers", json={"name": "Acme Ltd"}, headers=headers)
    r = client.post("/api/suppliers", json={"name": "acme limited"}, headers=headers)
    assert r.status_code == 400
    assert "name" in r.get_json()["fields"]


def test_a_supplier_needs_a_name(client, app, account):
    _user, headers = account
    assert client.post("/api/suppliers", json={}, headers=headers).status_code == 400
    assert client.post("/api/suppliers", json={"name": "  "},
                       headers=headers).status_code == 400


@pytest.mark.parametrize("field,value", [
    ("country", "Nigeria"), ("currency", "naira"), ("status", "deleted"),
])
def test_invalid_values_are_refused(client, app, account, field, value):
    _user, headers = account
    created = client.post("/api/suppliers", json={"name": "Val Co"},
                          headers=headers).get_json()["supplier"]
    r = client.patch(f"/api/suppliers/{created['id']}", json={field: value},
                     headers=headers)
    assert r.status_code == 400
    assert field in r.get_json()["fields"]


def test_archiving_does_not_delete(client, app, monkeypatch, account):
    """A supplier with invoices cannot be removed without orphaning history."""
    _user, headers = account
    _upload(client, app, monkeypatch, headers)
    supplier_id = _suppliers(client, headers)["suppliers"][0]["id"]

    assert client.delete(f"/api/suppliers/{supplier_id}", headers=headers).status_code == 200
    assert _suppliers(client, headers)["suppliers"] == []           # hidden by default
    archived = _suppliers(client, headers, status="archived")["suppliers"]
    assert len(archived) == 1
    # And the invoice still resolves.
    r = client.get(f"/api/suppliers/{supplier_id}", headers=headers)
    assert r.status_code == 200
    assert r.get_json()["supplier"]["stats"]["invoiceCount"] == 1


# ─── Statistics ──────────────────────────────────────────────────────────────
def test_totals_are_reported_per_currency(client, app, monkeypatch, account):
    """One total across mixed currencies is a meaningless number that looks
    authoritative."""
    _user, headers = account
    _upload(client, app, monkeypatch, headers, content=b"a")
    _upload(client, app, monkeypatch, headers, content=b"b", payload=_invoice(
        invoice_number="INV-2", currency="NGN", subtotal=5000, total=5000,
        line_items=[{"description": "x", "quantity": 1, "unit_price": 5000,
                     "amount": 5000}],
    ))
    supplier_id = _suppliers(client, headers)["suppliers"][0]["id"]
    stats = client.get(f"/api/suppliers/{supplier_id}",
                       headers=headers).get_json()["supplier"]["stats"]

    assert stats["invoiceCount"] == 2
    by_currency = {t["currency"]: t["total"] for t in stats["totalsByCurrency"]}
    assert by_currency == {"USD": "100.00", "NGN": "5000.00"}


def test_a_suppliers_invoices_can_be_listed(client, app, monkeypatch, account):
    _user, headers = account
    _upload(client, app, monkeypatch, headers)
    supplier_id = _suppliers(client, headers)["suppliers"][0]["id"]
    r = client.get(f"/api/suppliers/{supplier_id}/invoices", headers=headers)
    assert r.status_code == 200
    assert len(r.get_json()["invoices"]) == 1


# ─── Bank details: permission-gated ──────────────────────────────────────────
def test_an_owner_sees_bank_details(client, app, monkeypatch, account):
    _user, headers = account
    _upload(client, app, monkeypatch, headers)
    supplier_id = _suppliers(client, headers)["suppliers"][0]["id"]
    body = client.get(f"/api/suppliers/{supplier_id}", headers=headers).get_json()
    assert body["supplier"]["bankDetails"]["accountNumber"] == "0123456789"


def test_a_role_without_the_bank_permission_gets_no_key_at_all(
    client, app, monkeypatch, account
):
    """Omitted, not nulled: a key that is present-but-empty still confirms the
    details exist."""
    owner, owner_headers = account
    shared = make_org(app, owner, name="Shared", plan="pro")
    clerk = make_user(app, email="clerk@example.com", plan="pro")
    join_org(app, shared, clerk, role="accountant")   # has suppliers:read, not bank

    created = client.post("/api/suppliers", json={
        "name": "Bank Co",
        "bankDetails": {"accountNumber": "999", "bankName": "Zenith"},
    }, headers=org_header(app, owner, shared)).get_json()["supplier"]

    body = client.get(f"/api/suppliers/{created['id']}",
                      headers=org_header(app, clerk, shared)).get_json()
    assert "bankDetails" not in body["supplier"]
    assert body["supplier"]["name"] == "Bank Co"      # the rest is visible


def test_changing_payment_details_needs_the_bank_permission(
    client, app, monkeypatch, account
):
    """Rewriting where money is sent is the most abusable edit on this record."""
    owner, _owner_headers = account
    shared = make_org(app, owner, name="Shared2", plan="pro")
    clerk = make_user(app, email="clerk2@example.com", plan="pro")
    join_org(app, shared, clerk, role="accountant")

    created = client.post("/api/suppliers", json={"name": "Pay Co"},
                          headers=org_header(app, owner, shared)).get_json()["supplier"]

    r = client.patch(
        f"/api/suppliers/{created['id']}",
        json={"bankDetails": {"accountNumber": "ATTACKER-1"}},
        headers=org_header(app, clerk, shared),
    )
    assert r.status_code == 403

    with app.app_context():
        assert Supplier.query.get(created["id"]).bank_account_number is None


def test_an_extraction_never_silently_rewrites_known_bank_details(
    client, app, monkeypatch, account
):
    """This is the invoice-redirection fraud path: a scanned document that
    quietly replaces where the money goes."""
    _user, headers = account
    _upload(client, app, monkeypatch, headers, content=b"a")
    supplier_id = _suppliers(client, headers)["suppliers"][0]["id"]

    _upload(client, app, monkeypatch, headers, content=b"b", payload=_invoice(
        invoice_number="INV-2",
        vendor={**VENDOR, "bank_details": {
            "bank_name": "Attacker Bank", "account_name": "Not Acme",
            "account_number": "666", "iban": None, "swift": None,
            "sort_code": None,
        }},
    ))
    body = client.get(f"/api/suppliers/{supplier_id}", headers=headers).get_json()
    assert body["supplier"]["bankDetails"]["accountNumber"] == "0123456789"


# ─── Duplicate suppliers ─────────────────────────────────────────────────────
def test_suppliers_sharing_a_tax_id_are_flagged(client, app, account):
    _user, headers = account
    client.post("/api/suppliers", json={"name": "Acme Ltd", "taxId": "TIN-7"},
                headers=headers)
    client.post("/api/suppliers", json={"name": "Acme Trading", "taxId": "TIN-7"},
                headers=headers)

    found = client.get("/api/suppliers/duplicates", headers=headers).get_json()
    assert any(d["reason"] == "same_tax_id" for d in found["duplicates"])


def test_similar_names_are_flagged(client, app, account):
    _user, headers = account
    client.post("/api/suppliers", json={"name": "Acme"}, headers=headers)
    client.post("/api/suppliers", json={"name": "Acme Industrial Supplies"},
                headers=headers)
    found = client.get("/api/suppliers/duplicates", headers=headers).get_json()
    assert any(d["reason"] == "similar_name" for d in found["duplicates"])


def test_unrelated_suppliers_are_not_flagged(client, app, account):
    _user, headers = account
    client.post("/api/suppliers", json={"name": "Acme"}, headers=headers)
    client.post("/api/suppliers", json={"name": "Zenith Trading"}, headers=headers)
    found = client.get("/api/suppliers/duplicates", headers=headers).get_json()
    assert found["duplicates"] == []


# ─── Search and isolation ────────────────────────────────────────────────────
def test_suppliers_can_be_searched(client, app, account):
    _user, headers = account
    client.post("/api/suppliers", json={"name": "Acme Ltd", "taxId": "TIN-A"},
                headers=headers)
    client.post("/api/suppliers", json={"name": "Zenith"}, headers=headers)

    assert len(_suppliers(client, headers, q="acme")["suppliers"]) == 1
    assert len(_suppliers(client, headers, q="TIN-A")["suppliers"]) == 1


def test_suppliers_never_cross_organizations(client, app, monkeypatch):
    alice = make_user(app, email="asu@example.com", plan="pro")
    bob = make_user(app, email="bsu@example.com", plan="pro")
    _upload(client, app, monkeypatch, auth_header(app, alice))

    assert _suppliers(client, auth_header(app, bob))["suppliers"] == []


def test_the_same_supplier_name_in_two_organizations_is_two_records(
    client, app, monkeypatch
):
    """The uniqueness constraint is per organization, not global."""
    alice = make_user(app, email="asu2@example.com", plan="pro")
    bob = make_user(app, email="bsu2@example.com", plan="pro")
    _upload(client, app, monkeypatch, auth_header(app, alice))
    _upload(client, app, monkeypatch, auth_header(app, bob))

    assert len(_suppliers(client, auth_header(app, alice))["suppliers"]) == 1
    assert len(_suppliers(client, auth_header(app, bob))["suppliers"]) == 1


def test_cannot_read_another_organizations_supplier(client, app, monkeypatch):
    alice = make_user(app, email="asu3@example.com", plan="pro")
    bob = make_user(app, email="bsu3@example.com", plan="pro")
    _upload(client, app, monkeypatch, auth_header(app, alice))
    supplier_id = _suppliers(client, auth_header(app, alice))["suppliers"][0]["id"]

    r = client.get(f"/api/suppliers/{supplier_id}", headers=auth_header(app, bob))
    assert r.status_code == 404


def test_a_viewer_cannot_create_or_edit_suppliers(client, app, account):
    owner, _headers = account
    shared = make_org(app, owner, name="Shared3", plan="pro")
    viewer = make_user(app, email="viewer3@example.com", plan="pro")
    join_org(app, shared, viewer, role="viewer")

    r = client.post("/api/suppliers", json={"name": "Nope"},
                    headers=org_header(app, viewer, shared))
    assert r.status_code == 403
    # ...but can still read the list.
    assert client.get("/api/suppliers",
                      headers=org_header(app, viewer, shared)).status_code == 200
