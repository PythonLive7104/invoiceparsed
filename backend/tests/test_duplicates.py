"""Duplicate invoice detection.

Paying an invoice twice is the expensive error this prevents. But the opposite
error matters too: a supplier can legitimately bill the same amount twice in a
day, so these tests check just as hard that genuine invoices are NOT blocked,
and that nothing is ever deleted automatically.
"""
import io

import pytest

import duplicates as dup
from invoice_schema import normalize
from tests.conftest import auth_header, make_user

INVOICE = {
    "vendor": {"name": "Acme Supplies Ltd", "email": "ar@acme.example",
               "address": "1 Trade St", "tax_id": "TIN-1"},
    "invoice_number": "INV-2026-001",
    "invoice_date": "2026-10-15",
    "due_date": "2026-11-14",
    "currency": "USD",
    "line_items": [{"description": "Paper", "quantity": 1, "unit_price": 100,
                    "amount": 100}],
    "subtotal": 100, "tax": 0, "tax_percentage": 0, "total": 100,
    "confidence": {},
}


def _payload(**overrides):
    data = {**INVOICE, **overrides}
    if "vendor" in overrides and isinstance(overrides["vendor"], str):
        data["vendor"] = {**INVOICE["vendor"], "name": overrides["vendor"]}
    return normalize(data)


def _upload(client, app, monkeypatch, headers, payload=None, content=b"same-bytes",
            name="inv.pdf"):
    import routes.extract_routes as er
    monkeypatch.setattr(
        "openai_service.extract_document",
        lambda pages, doc_type="invoice": payload or normalize(INVOICE),
    )
    r = client.post(
        "/api/extract",
        data={"file": (io.BytesIO(content), name)},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert r.status_code == 200, r.get_json()
    return r.get_json()


@pytest.fixture
def account(app):
    user = make_user(app, email="dup@example.com", plan="pro")
    return user, auth_header(app, user)


# ─── The pure helpers ────────────────────────────────────────────────────────
def test_file_hash_is_order_sensitive():
    """The same pages in a different order are a different document."""
    a = dup.file_hash([{"bytes": b"one"}, {"bytes": b"two"}])
    b = dup.file_hash([{"bytes": b"two"}, {"bytes": b"one"}])
    assert a != b
    assert a == dup.file_hash([{"bytes": b"one"}, {"bytes": b"two"}])


@pytest.mark.parametrize("a,b", [
    ("Acme Supplies Ltd", "acme supplies limited"),
    ("ACME Supplies, Ltd.", "Acme Supplies"),
    ("Acme Supplies PLC", "acme   supplies"),
])
def test_supplier_names_normalize_to_the_same_key(a, b):
    assert dup.normalize_supplier(a) == dup.normalize_supplier(b)


def test_different_suppliers_stay_different():
    assert dup.normalize_supplier("Acme Ltd") != dup.normalize_supplier("Acorn Ltd")


@pytest.mark.parametrize("a,b", [
    ("INV-2026-001", "inv2026001"),
    ("INV 2026 001", "INV-2026-001"),
])
def test_invoice_numbers_normalize(a, b):
    assert dup.normalize_number(a) == dup.normalize_number(b)


def test_different_numbers_stay_different():
    assert dup.normalize_number("INV-1") != dup.normalize_number("INV-2")


# ─── Detection levels ────────────────────────────────────────────────────────
def test_identical_file_is_an_exact_duplicate(client, app, monkeypatch, account):
    _user, headers = account
    _upload(client, app, monkeypatch, headers, content=b"identical")
    second = _upload(client, app, monkeypatch, headers, content=b"identical")

    dups = second["duplicates"]
    assert len(dups) == 1
    assert dups[0]["reason"] == dup.EXACT_FILE
    assert dups[0]["score"] == 1.0
    assert "identical" in dups[0]["detail"].lower()


def test_same_supplier_and_number_is_flagged(client, app, monkeypatch, account):
    """Different scan of the same invoice: different bytes, same reference."""
    _user, headers = account
    _upload(client, app, monkeypatch, headers, content=b"scan-one")
    second = _upload(client, app, monkeypatch, headers, content=b"scan-two")

    reasons = {d["reason"] for d in second["duplicates"]}
    assert dup.SAME_NUMBER in reasons


def test_same_supplier_amount_and_date_is_flagged(client, app, monkeypatch, account):
    _user, headers = account
    _upload(client, app, monkeypatch, headers, content=b"a")
    second = _upload(
        client, app, monkeypatch, headers, content=b"b",
        payload=_payload(invoice_number="DIFFERENT-99"),
    )
    reasons = {d["reason"] for d in second["duplicates"]}
    assert dup.SAME_AMOUNT_DATE in reasons


def test_same_supplier_and_amount_days_apart_is_only_similar(
    client, app, monkeypatch, account
):
    _user, headers = account
    _upload(client, app, monkeypatch, headers, content=b"a")
    second = _upload(
        client, app, monkeypatch, headers, content=b"b",
        payload=_payload(invoice_number="OTHER-1", invoice_date="2026-10-17"),
    )
    found = second["duplicates"]
    assert found and found[0]["reason"] == dup.SIMILAR
    assert found[0]["score"] < 0.8


def test_the_strongest_reason_wins_for_a_pair(client, app, monkeypatch, account):
    """An identical file also matches on number and amount; it must be reported
    once, as the exact-file match, not three times."""
    _user, headers = account
    _upload(client, app, monkeypatch, headers, content=b"same")
    second = _upload(client, app, monkeypatch, headers, content=b"same")
    assert len(second["duplicates"]) == 1
    assert second["duplicates"][0]["reason"] == dup.EXACT_FILE


# ─── Not duplicates ──────────────────────────────────────────────────────────
def test_a_genuinely_different_invoice_is_not_flagged(client, app, monkeypatch, account):
    _user, headers = account
    _upload(client, app, monkeypatch, headers, content=b"a")
    second = _upload(
        client, app, monkeypatch, headers, content=b"b",
        payload=_payload(invoice_number="INV-2026-002", invoice_date="2026-11-20",
                         subtotal=250, total=250,
                         line_items=[{"description": "Other", "quantity": 1,
                                      "unit_price": 250, "amount": 250}]),
    )
    assert second["duplicates"] == []


def test_a_different_supplier_with_the_same_amount_is_not_flagged(
    client, app, monkeypatch, account
):
    """Two suppliers billing 100.00 on the same day is ordinary."""
    _user, headers = account
    _upload(client, app, monkeypatch, headers, content=b"a")
    second = _upload(
        client, app, monkeypatch, headers, content=b"b",
        payload=_payload(vendor="Totally Different Corp", invoice_number="XYZ-1"),
    )
    assert second["duplicates"] == []


def test_the_first_upload_is_never_a_duplicate(client, app, monkeypatch, account):
    _user, headers = account
    first = _upload(client, app, monkeypatch, headers)
    assert first["duplicates"] == []


# ─── Tenant isolation ────────────────────────────────────────────────────────
def test_duplicates_never_cross_organizations(client, app, monkeypatch):
    """A match against another tenant would not be a duplicate - it would be a
    data leak, telling one customer what another uploaded."""
    alice = make_user(app, email="a@example.com", plan="pro")
    bob = make_user(app, email="b@example.com", plan="pro")

    _upload(client, app, monkeypatch, auth_header(app, alice), content=b"identical")
    bobs = _upload(client, app, monkeypatch, auth_header(app, bob), content=b"identical")
    assert bobs["duplicates"] == []


# ─── Review workflow ─────────────────────────────────────────────────────────
def test_nothing_is_deleted_automatically(client, app, monkeypatch, account):
    """Refusing a legitimate invoice is worse than the error being prevented."""
    _user, headers = account
    first = _upload(client, app, monkeypatch, headers, content=b"same")
    second = _upload(client, app, monkeypatch, headers, content=b"same")

    for eid in (first["id"], second["id"]):
        assert client.get(f"/api/extractions/{eid}", headers=headers).status_code == 200
    rows = client.get("/api/extractions", headers=headers).get_json()["extractions"]
    assert len(rows) == 2


def test_dismissing_a_match_stops_it_being_reported(client, app, monkeypatch, account):
    """Re-showing a warning someone has already judged teaches them to ignore
    all of them."""
    _user, headers = account
    _upload(client, app, monkeypatch, headers, content=b"same")
    second = _upload(client, app, monkeypatch, headers, content=b"same")
    match_id = second["duplicates"][0]["id"]

    r = client.post(
        f"/api/extractions/{second['id']}/duplicates/{match_id}",
        json={"status": "dismissed"}, headers=headers,
    )
    assert r.status_code == 200
    assert r.get_json()["duplicates"] == []

    reloaded = client.get(f"/api/extractions/{second['id']}", headers=headers).get_json()
    assert reloaded["duplicates"] == []


def test_confirming_a_match_keeps_it_visible_and_deletes_nothing(
    client, app, monkeypatch, account
):
    _user, headers = account
    first = _upload(client, app, monkeypatch, headers, content=b"same")
    second = _upload(client, app, monkeypatch, headers, content=b"same")
    match_id = second["duplicates"][0]["id"]

    r = client.post(
        f"/api/extractions/{second['id']}/duplicates/{match_id}",
        json={"status": "confirmed"}, headers=headers,
    )
    assert r.status_code == 200
    assert r.get_json()["duplicate"]["status"] == "confirmed"
    # Both documents still exist: the decision is recorded, not acted on.
    assert client.get(f"/api/extractions/{first['id']}", headers=headers).status_code == 200
    assert client.get(f"/api/extractions/{second['id']}", headers=headers).status_code == 200


def test_an_invalid_decision_is_rejected(client, app, monkeypatch, account):
    _user, headers = account
    _upload(client, app, monkeypatch, headers, content=b"same")
    second = _upload(client, app, monkeypatch, headers, content=b"same")
    match_id = second["duplicates"][0]["id"]
    r = client.post(
        f"/api/extractions/{second['id']}/duplicates/{match_id}",
        json={"status": "deleted"}, headers=headers,
    )
    assert r.status_code == 400


def test_cannot_resolve_another_tenants_match(client, app, monkeypatch):
    alice = make_user(app, email="a2@example.com", plan="pro")
    bob = make_user(app, email="b2@example.com", plan="pro")
    a_headers = auth_header(app, alice)

    _upload(client, app, monkeypatch, a_headers, content=b"same")
    second = _upload(client, app, monkeypatch, a_headers, content=b"same")
    match_id = second["duplicates"][0]["id"]

    r = client.post(
        f"/api/extractions/{second['id']}/duplicates/{match_id}",
        json={"status": "dismissed"}, headers=auth_header(app, bob),
    )
    assert r.status_code == 404


def test_the_review_queue_lists_pending_matches(client, app, monkeypatch, account):
    _user, headers = account
    _upload(client, app, monkeypatch, headers, content=b"same")
    _upload(client, app, monkeypatch, headers, content=b"same")

    queue = client.get("/api/duplicates", headers=headers).get_json()["duplicates"]
    assert len(queue) == 1
    entry = queue[0]
    # Enough to review without opening either document.
    assert entry["match"]["fileName"]
    assert entry["extraction"]["fileName"]
    assert entry["detail"]


def test_a_deleted_counterpart_drops_out_of_the_warning(
    client, app, monkeypatch, account
):
    """Soft-deleting the earlier document must not leave a warning pointing at
    something the user can no longer open."""
    _user, headers = account
    first = _upload(client, app, monkeypatch, headers, content=b"same")
    second = _upload(client, app, monkeypatch, headers, content=b"same")
    assert second["duplicates"]

    assert client.delete(f"/api/extractions/{first['id']}", headers=headers).status_code == 200
    reloaded = client.get(f"/api/extractions/{second['id']}", headers=headers).get_json()
    assert reloaded["duplicates"] == []
