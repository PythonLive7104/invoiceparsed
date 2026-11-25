"""Payment tracking (P2.6).

The thing this module must never do is as important as what it does: it
records payments, it does not make them. There is a test for that below, and
it is not a formality — "architected for later integrations" is exactly how a
product acquires the ability to move money without anybody deciding to.

The rest is weighted toward the arithmetic that gets an invoice paid twice:
a position recomputed rather than incremented, a voided payment that gives its
money back, and an overpayment that is reported rather than swallowed.

Every fixture runs on the **Pro** plan: payables is a Pro capability.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from roles import ACCOUNTANT, VIEWER
from tests.conftest import auth_header, join_org, make_org, make_user, org_header


@pytest.fixture
def owner(app):
    return make_user(app, email="owner@example.com", plan="pro")


@pytest.fixture
def supplier(app, owner):
    from extensions import db
    from models import Supplier
    from suppliers import match_key_for

    with app.app_context():
        row = Supplier(
            organization_id=owner["organization_id"],
            name="Acme Supplies Ltd",
            match_key=match_key_for("Acme Supplies Ltd"),
            currency="NGN",
        )
        db.session.add(row)
        db.session.commit()
        return {"id": row.id, "name": row.name}


def make_invoice(app, owner, *, total="1000.00", due_date=None, number="INV-001",
                 supplier_id=None, name="inv.pdf", currency="NGN"):
    from documents import apply_headline_fields
    from extensions import db
    from invoice_schema import normalize
    from models import Extraction

    document = normalize({
        "vendor": {"name": "Acme Supplies Ltd"},
        "invoice_number": number,
        "invoice_date": "2026-11-01",
        "due_date": due_date,
        "currency": currency,
        "line_items": [{"description": "Widget", "quantity": 1,
                        "unit_price": total, "amount": total}],
        "subtotal": total, "tax": 0, "total": total,
        "confidence": {},
    })
    with app.app_context():
        row = Extraction(
            organization_id=owner["organization_id"],
            user_id=owner["id"],
            doc_type="invoice",
            file_name=name,
            file_type="application/pdf",
            file_size=100,
            supplier_id=supplier_id,
            data="{}",
            status="completed",
        )
        apply_headline_fields(row, document)
        db.session.add(row)
        db.session.commit()
        return row.id


def pay(client, headers, eid, amount, **extra):
    body = {"amount": str(amount)}
    body.update(extra)
    return client.post(f"/api/payments/invoices/{eid}", json=body, headers=headers)


def position(client, headers, eid):
    return client.get(f"/api/payments/invoices/{eid}", headers=headers).get_json()


# ─── The boundary ────────────────────────────────────────────────────────────
def test_nothing_in_this_module_can_move_money(app):
    """The product records payments; it does not make them.

    Asserted on the source rather than behaviourally, because the failure this
    guards against is a future change that ADDS the ability — and the moment
    software can move money out of a business it becomes the most valuable
    thing in the building to compromise.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    for name in ("payments.py", "routes/payment_routes.py"):
        source = (root / name).read_text(encoding="utf-8").lower()
        for forbidden in ("requests.post", "httpx", "urlopen", "bachs",
                          "stripe", "paystack", "transfer_api"):
            assert forbidden not in source, (name, forbidden)


# ─── Recording ───────────────────────────────────────────────────────────────
def test_recording_a_payment_moves_the_invoice_to_partially_paid(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])

    response = pay(client, headers, eid, "400.00", reference="FT-9001")
    assert response.status_code == 201
    body = response.get_json()
    assert body["amountPaid"] == "400.00"
    assert body["outstanding"] == "600.00"
    assert body["state"] == "partially_paid"
    assert body["payments"][0]["reference"] == "FT-9001"


def test_paying_in_full_settles_the_invoice(app, client, owner, supplier):
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])
    pay(client, headers, eid, "600.00")
    body = pay(client, headers, eid, "400.00").get_json()
    assert body["amountPaid"] == "1000.00"
    assert body["outstanding"] == "0.00"
    assert body["state"] == "paid"


def test_a_penny_short_still_counts_as_settled(app, client, owner, supplier):
    """Suppliers round, banks round, and chasing a cent costs more than the
    cent."""
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])
    body = pay(client, headers, eid, "999.99").get_json()
    assert body["state"] == "paid"


def test_two_pence_short_does_not(app, client, owner, supplier):
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])
    body = pay(client, headers, eid, "999.98").get_json()
    assert body["state"] == "partially_paid"


def test_a_zero_or_negative_payment_is_refused(app, client, owner, supplier):
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])
    for amount in ("0", "-50.00"):
        response = pay(client, headers, eid, amount)
        assert response.status_code == 400
        assert "amount" in response.get_json()["fields"]


def test_a_payment_dated_in_the_future_is_refused(app, client, owner, supplier):
    """Recording a payment that has not happened turns a ledger into a plan."""
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    response = pay(client, headers, eid, "100.00", paidOn=tomorrow)
    assert response.status_code == 400
    assert "paidOn" in response.get_json()["fields"]


def test_an_unknown_method_is_refused(app, client, owner, supplier):
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])
    response = pay(client, headers, eid, "100.00", method="carrier_pigeon")
    assert response.status_code == 400
    assert "method" in response.get_json()["fields"]


def test_an_overpayment_is_recorded_and_flagged_not_refused(
    app, client, owner, supplier
):
    """Refusing to record money that has already left the bank account would
    make this ledger disagree with the bank."""
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])
    response = pay(client, headers, eid, "1500.00")
    assert response.status_code == 201
    body = response.get_json()
    assert body["amountPaid"] == "1500.00"
    assert "warning" in body
    assert "500.00" in body["warning"]
    # Outstanding never goes negative: an overpayment is a credit to chase,
    # not a negative debt.
    assert body["outstanding"] == "0.00"
    assert body["state"] == "paid"


def test_the_exact_amounts_survive_the_round_trip(app, client, owner, supplier):
    """Decimal strings, never JSON numbers, or a JavaScript client reads them
    back as doubles."""
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, total="9007199254740.99",
                       supplier_id=supplier["id"])
    body = pay(client, headers, eid, "9007199254740.99").get_json()
    assert body["amountPaid"] == "9007199254740.99"
    assert body["outstanding"] == "0.00"
    assert isinstance(body["amountPaid"], str)
    assert isinstance(body["payments"][0]["amount"], str)


# ─── Voiding ─────────────────────────────────────────────────────────────────
def test_voiding_a_payment_gives_the_money_back(app, client, owner, supplier):
    """The reason the position is recomputed rather than incremented."""
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])
    recorded = pay(client, headers, eid, "1000.00").get_json()
    assert recorded["state"] == "paid"
    payment_id = recorded["payments"][0]["id"]

    voided = client.post(f"/api/payments/{payment_id}/void",
                         json={"reason": "Keyed against the wrong invoice."},
                         headers=headers)
    assert voided.status_code == 200
    body = voided.get_json()
    assert body["amountPaid"] == "0.00"
    assert body["outstanding"] == "1000.00"
    assert body["state"] == "unpaid"


def test_a_voided_payment_is_kept_as_a_record(app, client, owner, supplier):
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])
    recorded = pay(client, headers, eid, "500.00").get_json()
    payment_id = recorded["payments"][0]["id"]
    client.post(f"/api/payments/{payment_id}/void",
                json={"reason": "Duplicate."}, headers=headers)

    body = position(client, headers, eid)
    assert len(body["payments"]) == 1
    assert body["payments"][0]["void"] is True
    assert body["payments"][0]["voidReason"] == "Duplicate."


def test_voiding_needs_a_reason(app, client, owner, supplier):
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])
    payment_id = pay(client, headers, eid, "100.00").get_json()["payments"][0]["id"]
    response = client.post(f"/api/payments/{payment_id}/void", json={},
                           headers=headers)
    assert response.status_code == 400
    assert response.get_json()["code"] == "REASON_REQUIRED"


def test_a_payment_cannot_be_voided_twice(app, client, owner, supplier):
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])
    payment_id = pay(client, headers, eid, "100.00").get_json()["payments"][0]["id"]
    client.post(f"/api/payments/{payment_id}/void", json={"reason": "x"},
                headers=headers)
    again = client.post(f"/api/payments/{payment_id}/void",
                        json={"reason": "x"}, headers=headers)
    assert again.status_code == 409
    assert again.get_json()["code"] == "ALREADY_VOID"


def test_voiding_one_of_several_leaves_the_others(app, client, owner, supplier):
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])
    first = pay(client, headers, eid, "400.00").get_json()["payments"][0]["id"]
    pay(client, headers, eid, "600.00")

    client.post(f"/api/payments/{first}/void", json={"reason": "dup"},
                headers=headers)
    body = position(client, headers, eid)
    assert body["amountPaid"] == "600.00"
    assert body["state"] == "partially_paid"


# ─── Overdue ─────────────────────────────────────────────────────────────────
def test_an_invoice_past_its_due_date_is_overdue(app, client, owner, supplier):
    headers = auth_header(app, owner)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    eid = make_invoice(app, owner, due_date=yesterday, supplier_id=supplier["id"])

    body = client.get("/api/payments", headers=headers).get_json()
    row = next(item for item in body["items"] if item["extractionId"] == eid)
    assert row["state"] == "overdue"


def test_overdue_outranks_partially_paid(app, client, owner, supplier):
    """The useful question is "what is late", not "what is untouched"."""
    headers = auth_header(app, owner)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    eid = make_invoice(app, owner, due_date=yesterday, supplier_id=supplier["id"])
    body = pay(client, headers, eid, "100.00").get_json()
    assert body["state"] == "overdue"


def test_paying_an_overdue_invoice_settles_it(app, client, owner, supplier):
    headers = auth_header(app, owner)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    eid = make_invoice(app, owner, due_date=yesterday, supplier_id=supplier["id"])
    body = pay(client, headers, eid, "1000.00").get_json()
    assert body["state"] == "paid"


def test_an_invoice_due_today_is_not_yet_overdue(app, client, owner, supplier):
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, due_date=date.today().isoformat(),
                       supplier_id=supplier["id"])
    body = client.get("/api/payments", headers=headers).get_json()
    row = next(item for item in body["items"] if item["extractionId"] == eid)
    assert row["state"] == "unpaid"


def test_overdue_is_refreshed_as_the_calendar_moves(app, owner, supplier):
    """The one state that changes without anybody touching anything."""
    from extensions import db
    from models import Extraction
    from payments import payment_state, refresh_overdue

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    eid = make_invoice(app, owner, due_date=yesterday, supplier_id=supplier["id"])
    with app.app_context():
        row = Extraction.query.filter_by(id=eid).first()
        row.payment_state = "unpaid"
        db.session.commit()

        changed = refresh_overdue(owner["organization_id"])
        db.session.commit()
        assert changed == 1
        assert Extraction.query.filter_by(id=eid).first().payment_state == "overdue"

        # And a pure function of the row, testable without any of this.
        row = Extraction.query.filter_by(id=eid).first()
        assert payment_state(row, today=date(2020, 1, 1)) == "unpaid"


# ─── Disputes ────────────────────────────────────────────────────────────────
def test_a_disputed_invoice_outranks_every_other_state(
    app, client, owner, supplier
):
    """An invoice somebody is arguing about must not sit quietly in
    'overdue' where a payment run will sweep it up."""
    headers = auth_header(app, owner)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    eid = make_invoice(app, owner, due_date=yesterday, supplier_id=supplier["id"])
    pay(client, headers, eid, "100.00")

    disputed = client.post(f"/api/payments/invoices/{eid}/dispute",
                           json={"reason": "Goods never arrived."},
                           headers=headers)
    assert disputed.status_code == 200
    body = disputed.get_json()
    assert body["state"] == "disputed"
    assert body["disputed"] is True
    assert body["disputeReason"] == "Goods never arrived."


def test_a_dispute_needs_a_reason(app, client, owner, supplier):
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])
    response = client.post(f"/api/payments/invoices/{eid}/dispute",
                           json={"reason": "  "}, headers=headers)
    assert response.status_code == 400


def test_clearing_a_dispute_returns_the_invoice_to_its_figures(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])
    pay(client, headers, eid, "400.00")
    client.post(f"/api/payments/invoices/{eid}/dispute",
                json={"reason": "Short delivery."}, headers=headers)

    cleared = client.delete(f"/api/payments/invoices/{eid}/dispute",
                            headers=headers)
    assert cleared.status_code == 200
    body = cleared.get_json()
    assert body["disputed"] is False
    assert body["state"] == "partially_paid"


def test_clearing_a_dispute_that_does_not_exist_is_refused(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])
    response = client.delete(f"/api/payments/invoices/{eid}/dispute",
                             headers=headers)
    assert response.status_code == 409
    assert response.get_json()["code"] == "NOT_DISPUTED"


# ─── The list and the summary ────────────────────────────────────────────────
def test_the_list_can_be_filtered_by_state(app, client, owner, supplier):
    headers = auth_header(app, owner)
    unpaid = make_invoice(app, owner, number="INV-1", name="a.pdf",
                          supplier_id=supplier["id"])
    settled = make_invoice(app, owner, number="INV-2", name="b.pdf",
                           supplier_id=supplier["id"])
    pay(client, headers, settled, "1000.00")

    open_only = client.get("/api/payments?state=open", headers=headers).get_json()
    assert [row["extractionId"] for row in open_only["items"]] == [unpaid]

    paid_only = client.get("/api/payments?state=paid", headers=headers).get_json()
    assert [row["extractionId"] for row in paid_only["items"]] == [settled]


def test_the_summary_totals_outstanding_per_currency(app, client, owner, supplier):
    """One total spanning NGN and USD is a meaningless number that looks
    authoritative."""
    headers = auth_header(app, owner)
    make_invoice(app, owner, total="1000.00", currency="NGN", number="N1",
                 name="n1.pdf", supplier_id=supplier["id"])
    make_invoice(app, owner, total="250.00", currency="USD", number="U1",
                 name="u1.pdf", supplier_id=supplier["id"])

    body = client.get("/api/payments/summary", headers=headers).get_json()
    rows = {row["currency"]: row["amount"] for row in body["outstandingByCurrency"]}
    assert rows["NGN"] == "1000.00"
    assert rows["USD"] == "250.00"
    assert body["byState"]["unpaid"] == 2


def test_the_summary_excludes_what_has_been_paid(app, client, owner, supplier):
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])
    pay(client, headers, eid, "1000.00")

    body = client.get("/api/payments/summary", headers=headers).get_json()
    assert body["outstandingByCurrency"] == []
    assert body["byState"]["paid"] == 1


def test_a_partially_paid_invoice_contributes_only_what_is_left(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])
    pay(client, headers, eid, "400.00")

    body = client.get("/api/payments/summary", headers=headers).get_json()
    rows = {row["currency"]: row["amount"] for row in body["outstandingByCurrency"]}
    assert rows["NGN"] == "600.00"


def test_the_list_is_ordered_by_what_is_due_soonest(app, client, owner, supplier):
    headers = auth_header(app, owner)
    later = make_invoice(app, owner, due_date="2027-01-01", number="L",
                         name="l.pdf", supplier_id=supplier["id"])
    sooner = make_invoice(app, owner, due_date="2026-12-01", number="S",
                          name="s.pdf", supplier_id=supplier["id"])

    body = client.get("/api/payments", headers=headers).get_json()
    order = [row["extractionId"] for row in body["items"]]
    assert order.index(sooner) < order.index(later)


# ─── Permissions, tenancy and the paywall ────────────────────────────────────
def test_an_accountant_can_record_payments(app, client, owner):
    """Recording what the business paid is accounts-payable work."""
    org = make_org(app, owner, name="Acme", plan="pro")
    clerk = make_user(app, email="clerk@example.com", plan="pro")
    join_org(app, org, clerk, ACCOUNTANT)
    headers = {**auth_header(app, clerk), **org_header(app, clerk, org)}
    assert client.get("/api/payments", headers=headers).status_code == 200
    assert client.get("/api/payments/summary", headers=headers).status_code == 200


def test_a_viewer_cannot_record_a_payment(app, client, owner, supplier):
    org = make_org(app, owner, name="Watch Co", plan="pro")
    watcher = make_user(app, email="watcher@example.com", plan="pro")
    join_org(app, org, watcher, VIEWER)
    headers = {**auth_header(app, watcher), **org_header(app, watcher, org)}
    assert client.get("/api/payments", headers=headers).status_code == 200
    assert client.post("/api/payments/invoices/anything", json={"amount": "1"},
                       headers=headers).status_code == 403


def test_payments_never_cross_an_organization_boundary(app, client, owner, supplier):
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])
    pay(client, headers, eid, "100.00")

    stranger = make_user(app, email="stranger@example.com", plan="pro")
    stranger_headers = auth_header(app, stranger)
    assert client.get(f"/api/payments/invoices/{eid}",
                      headers=stranger_headers).status_code == 404
    assert client.get("/api/payments",
                      headers=stranger_headers).get_json()["total"] == 0


def test_a_deleted_invoice_leaves_the_payables_list(app, client, owner, supplier):
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])
    assert client.get("/api/payments", headers=headers).get_json()["total"] == 1
    client.delete(f"/api/extractions/{eid}", headers=headers)
    assert client.get("/api/payments", headers=headers).get_json()["total"] == 0


def test_payment_tracking_is_behind_the_payables_paywall(app, client):
    free = make_user(app, email="free@example.com", plan="free")
    response = client.get("/api/payments", headers=auth_header(app, free))
    assert response.status_code == 402
    assert response.get_json()["capability"] == "payables"


def test_the_arithmetic_is_exact_across_many_small_payments(
    app, client, owner, supplier
):
    """Ten payments of 0.1 must total exactly 1.00, which is the sum a float
    gets wrong."""
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, total="1.00", supplier_id=supplier["id"])
    for _ in range(10):
        pay(client, headers, eid, "0.10")

    body = position(client, headers, eid)
    assert body["amountPaid"] == "1.00"
    assert Decimal(body["amountPaid"]) == Decimal("1.00")
    assert body["state"] == "paid"
