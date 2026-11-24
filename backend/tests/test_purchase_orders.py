"""Purchase orders (P2.2).

Weighted toward the rules that protect money rather than the happy path:
totals that cannot be dictated by a client, an approved order that cannot be
edited, approval that is a separate capability from raising an order, and no
route by which one organization can see another's commitments.

Every fixture here runs on the **Pro** plan, because suppliers, purchase
orders and matching are a Pro capability (`plans.PAYABLES`). On a free or
starter plan every endpoint in this module answers 402, which is what
tests/test_payables_plan.py checks - so do not drop the `plan="pro"`
arguments below.
"""
from decimal import Decimal

import pytest

from roles import (
    ACCOUNTANT,
    APPROVER,
    FINANCE_MANAGER,
    PROCUREMENT,
    VIEWER,
)
from tests.conftest import auth_header, join_org, make_org, make_user, org_header


# ─── Fixtures and helpers ────────────────────────────────────────────────────
@pytest.fixture
def owner(app):
    return make_user(app, email="owner@example.com", plan="pro")


@pytest.fixture
def supplier(app, owner):
    """A supplier to order from, created directly so these tests do not depend
    on the supplier API."""
    from extensions import db
    from models import Supplier

    with app.app_context():
        row = Supplier(
            organization_id=owner["organization_id"],
            name="Acme Supplies Ltd",
            match_key="acme supplies",
            currency="NGN",
            payment_terms="Net 30",
            email="ar@acme.example",
            tax_id="TIN-99",
            address="12 Industrial Way\nLagos",
        )
        db.session.add(row)
        db.session.commit()
        return {"id": row.id, "name": row.name}


def make_supplier(app, organization_id, name="Other Vendor", key=None,
                  status="active", currency="USD"):
    from extensions import db
    from models import Supplier

    with app.app_context():
        row = Supplier(
            organization_id=organization_id,
            name=name,
            match_key=key or name.lower(),
            status=status,
            currency=currency,
        )
        db.session.add(row)
        db.session.commit()
        return {"id": row.id, "name": row.name}


LINE = {"description": "Widget", "quantity": "3", "unitPrice": "100.00", "taxRate": "7.5"}


def create_po(client, headers, supplier_id, lines=None, **extra):
    body = {"supplierId": supplier_id, "lines": lines if lines is not None else [LINE]}
    body.update(extra)
    return client.post("/api/purchase-orders", json=body, headers=headers)


def approve_chain(client, headers, po_id):
    """Submit and approve, the usual way an order becomes real."""
    client.post(f"/api/purchase-orders/{po_id}/submit", headers=headers)
    return client.post(f"/api/purchase-orders/{po_id}/approve", headers=headers)


# ─── Arithmetic ──────────────────────────────────────────────────────────────
def test_line_arithmetic_is_quantity_times_price_plus_tax(app):
    with app.app_context():
        from purchase_orders import compute_line

        subtotal, tax, total = compute_line("3", "100.00", "7.5")
        assert subtotal == Decimal("300.00")
        assert tax == Decimal("22.50")
        assert total == Decimal("322.50")


def test_each_line_is_rounded_before_the_lines_are_summed(app, client, owner, supplier):
    """The convention suppliers print, and therefore the one P2.3 must compare
    against.

    Three lines of 0.335 each round to 0.34 and total 1.02. Keeping full
    precision and rounding only the total would give 1.01 - a one-cent
    disagreement with the supplier's own invoice, which would raise a false
    mismatch on a perfectly good document.
    """
    lines = [
        {"description": f"Item {n}", "quantity": "1", "unitPrice": "0.335", "taxRate": "0"}
        for n in range(3)
    ]
    response = create_po(client, auth_header(app, owner), supplier["id"], lines=lines)
    assert response.status_code == 201
    po = response.get_json()["purchaseOrder"]

    assert [line["lineSubtotal"] for line in po["lines"]] == ["0.34"] * 3
    assert po["total"] == "1.02"
    assert po["total"] != "1.01"      # what rounding only at the end would give


def test_totals_are_computed_and_a_client_supplied_total_is_ignored(
    app, client, owner, supplier
):
    """The central integrity rule: a client cannot state what an order is worth."""
    response = create_po(
        client, auth_header(app, owner), supplier["id"],
        total="1.00", subtotal="1.00", taxTotal="0.00",
    )
    assert response.status_code == 201
    po = response.get_json()["purchaseOrder"]
    assert po["subtotal"] == "300.00"
    assert po["taxTotal"] == "22.50"
    assert po["total"] == "322.50"


def test_fractional_quantities_are_kept(app, client, owner, supplier):
    response = create_po(
        client, auth_header(app, owner), supplier["id"],
        lines=[{"description": "Steel", "quantity": "2.5", "unitPrice": "40.00",
                "taxRate": "0"}],
    )
    po = response.get_json()["purchaseOrder"]
    assert po["lines"][0]["quantity"] == "2.50"
    assert po["total"] == "100.00"


def test_money_is_returned_as_decimal_strings_never_json_numbers(
    app, client, owner, supplier
):
    """A JSON number would be read back as a double by every JS client, undoing
    the precision the Numeric columns exist to preserve."""
    import json

    response = create_po(client, auth_header(app, owner), supplier["id"])
    raw = json.loads(response.data)["purchaseOrder"]
    assert isinstance(raw["total"], str)
    assert isinstance(raw["lines"][0]["unitPrice"], str)
    assert isinstance(raw["lines"][0]["quantity"], str)


def test_zero_lines_gives_a_zero_total_not_a_null(app, client, owner, supplier):
    response = create_po(client, auth_header(app, owner), supplier["id"], lines=[])
    assert response.status_code == 201
    assert response.get_json()["purchaseOrder"]["total"] == "0.00"


# ─── Line validation ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("patch,field", [
    ({"description": ""}, "lines.0.description"),
    ({"description": "   "}, "lines.0.description"),
    ({"quantity": "0"}, "lines.0.quantity"),
    ({"quantity": "-2"}, "lines.0.quantity"),
    ({"quantity": "abc"}, "lines.0.quantity"),
    ({"quantity": None}, "lines.0.quantity"),
    ({"unitPrice": "-1"}, "lines.0.unitPrice"),
    ({"unitPrice": None}, "lines.0.unitPrice"),
    ({"taxRate": "-1"}, "lines.0.taxRate"),
    ({"taxRate": "101"}, "lines.0.taxRate"),
])
def test_bad_lines_are_rejected_per_field(app, client, owner, supplier, patch, field):
    """Errors are keyed per line and per field so the client can mark the
    offending cell rather than showing one message for the whole form."""
    line = {**LINE, **patch}
    response = create_po(client, auth_header(app, owner), supplier["id"], lines=[line])
    assert response.status_code == 400
    assert field in response.get_json()["fields"]


def test_a_quantity_of_zero_is_refused_because_it_orders_nothing(app):
    with app.app_context():
        from purchase_orders import validate_lines

        _, errors = validate_lines([{**LINE, "quantity": "0"}])
        assert "greater than zero" in errors["lines.0.quantity"]


def test_lines_must_be_a_list(app, client, owner, supplier):
    response = create_po(client, auth_header(app, owner), supplier["id"],
                         lines={"description": "not a list"})
    assert response.status_code == 400
    assert "lines" in response.get_json()["fields"]


def test_an_order_cannot_hold_an_unbounded_number_of_lines(app):
    with app.app_context():
        from purchase_orders import MAX_LINES, validate_lines

        _, errors = validate_lines([LINE] * (MAX_LINES + 1))
        assert "lines" in errors


def test_line_numbers_are_assigned_in_order(app, client, owner, supplier):
    lines = [{**LINE, "description": f"Item {n}"} for n in range(4)]
    response = create_po(client, auth_header(app, owner), supplier["id"], lines=lines)
    po = response.get_json()["purchaseOrder"]
    assert [line["lineNo"] for line in po["lines"]] == [1, 2, 3, 4]


def test_quantities_are_quantized_to_the_column_precision(app):
    """Four places, matching Numeric(18,4), so a client sending more precision
    than the column holds is rounded here rather than differently by each
    database engine."""
    with app.app_context():
        from purchase_orders import validate_lines

        clean, errors = validate_lines([{**LINE, "quantity": "1.123456789"}])
        assert not errors
        assert clean[0]["quantity"] == Decimal("1.1235")


# ─── Numbering ───────────────────────────────────────────────────────────────
def test_the_first_order_is_numbered_po_0001(app, client, owner, supplier):
    response = create_po(client, auth_header(app, owner), supplier["id"])
    assert response.get_json()["purchaseOrder"]["poNumber"] == "PO-0001"


def test_numbers_increment(app, client, owner, supplier):
    headers = auth_header(app, owner)
    numbers = [
        create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["poNumber"]
        for _ in range(3)
    ]
    assert numbers == ["PO-0001", "PO-0002", "PO-0003"]


def test_numbering_is_per_organization(app, client, owner, supplier):
    """Two organizations both start at PO-0001. Numbers are theirs, not ours."""
    other = make_org(app, owner, name="Second Co", plan="pro")
    other_supplier = make_supplier(app, other["id"], name="Vendor B")

    first = create_po(client, auth_header(app, owner), supplier["id"])
    second = create_po(client, org_header(app, owner, other), other_supplier["id"])

    assert first.get_json()["purchaseOrder"]["poNumber"] == "PO-0001"
    assert second.get_json()["purchaseOrder"]["poNumber"] == "PO-0001"


def test_an_organizations_own_numbering_scheme_is_honoured(app, client, owner, supplier):
    response = create_po(client, auth_header(app, owner), supplier["id"],
                         poNumber="REQ/2026/0042")
    assert response.status_code == 201
    assert response.get_json()["purchaseOrder"]["poNumber"] == "REQ/2026/0042"


def test_a_duplicate_number_is_refused(app, client, owner, supplier):
    """400 with a field key rather than a bare 409, so the form can mark the
    offending input. The 409 path behind it exists only for a genuine race -
    two creates passing the pre-check before either commits - which no
    pre-check can catch."""
    headers = auth_header(app, owner)
    create_po(client, headers, supplier["id"], poNumber="PO-X")
    response = create_po(client, headers, supplier["id"], poNumber="PO-X")
    assert response.status_code == 400
    assert "poNumber" in response.get_json()["fields"]


def test_a_number_already_taken_is_refused_on_edit_too(app, client, owner, supplier):
    headers = auth_header(app, owner)
    create_po(client, headers, supplier["id"], poNumber="PO-TAKEN")
    second = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]

    response = client.patch(f"/api/purchase-orders/{second}",
                            json={"poNumber": "PO-TAKEN"}, headers=headers)
    assert response.status_code == 400
    assert "poNumber" in response.get_json()["fields"]


def test_a_blank_number_cannot_be_set(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]

    response = client.patch(f"/api/purchase-orders/{po_id}",
                            json={"poNumber": "  "}, headers=headers)
    assert response.status_code == 400


def test_a_custom_number_does_not_disturb_the_generated_sequence(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    create_po(client, headers, supplier["id"], poNumber="REQ/ONE")
    response = create_po(client, headers, supplier["id"])
    assert response.get_json()["purchaseOrder"]["poNumber"] == "PO-0001"


def test_a_colliding_generated_number_is_retried_rather_than_failing(
    app, client, owner, supplier, monkeypatch
):
    """Two simultaneous creates can pick the same number. The unique constraint
    catches it and the create retries, which is cheaper than locking a counter
    on every write - but only if the retry actually re-stages the order and its
    lines after the rollback, which is what this asserts.
    """
    headers = auth_header(app, owner)
    create_po(client, headers, supplier["id"])          # takes PO-0001

    import routes.purchase_order_routes as module

    calls = {"n": 0}

    def flaky(organization_id):
        calls["n"] += 1
        return "PO-0001" if calls["n"] == 1 else "PO-0002"

    monkeypatch.setattr(module, "next_po_number", flaky)

    response = create_po(client, headers, supplier["id"])
    assert response.status_code == 201, response.get_json()
    po = response.get_json()["purchaseOrder"]
    assert po["poNumber"] == "PO-0002"
    assert calls["n"] == 2
    # The lines must have survived the rollback and been written with the order.
    assert len(po["lines"]) == 1
    assert po["total"] == "322.50"


def test_numbering_ignores_numbers_that_are_not_ours(app, client, owner, supplier):
    """An imported "PO-ABC" must not break the sequence."""
    headers = auth_header(app, owner)
    create_po(client, headers, supplier["id"], poNumber="PO-ABC")
    response = create_po(client, headers, supplier["id"])
    assert response.get_json()["purchaseOrder"]["poNumber"] == "PO-0001"


# ─── Create ──────────────────────────────────────────────────────────────────
def test_an_order_needs_a_supplier(app, client, owner):
    response = client.post("/api/purchase-orders", json={"lines": [LINE]},
                           headers=auth_header(app, owner))
    assert response.status_code == 400
    assert "supplierId" in response.get_json()["fields"]


def test_another_organizations_supplier_cannot_be_ordered_from(app, client, owner):
    """The supplier id is a secret of that organization; this must read as
    'does not exist', not 'exists but is not yours'."""
    stranger = make_user(app, email="stranger@example.com", plan="pro")
    foreign = make_supplier(app, stranger["organization_id"], name="Foreign Co")

    response = create_po(client, auth_header(app, owner), foreign["id"])
    assert response.status_code == 400
    assert "does not exist" in response.get_json()["fields"]["supplierId"]


def test_an_archived_supplier_cannot_be_ordered_from(app, client, owner):
    archived = make_supplier(app, make_user(app, email="o2@example.com", plan="pro")["organization_id"])
    # Same organization as the caller, but archived.
    owner_archived = make_supplier(
        app, _org_of(app, owner), name="Retired Co", status="archived"
    )
    assert archived  # the other-org supplier is irrelevant here

    response = create_po(client, auth_header(app, owner), owner_archived["id"])
    assert response.status_code == 400
    assert "archived" in response.get_json()["fields"]["supplierId"]


def _org_of(app, user):
    return user["organization_id"]


def test_currency_and_terms_default_from_the_supplier(app, client, owner, supplier):
    """What the invoice will arrive in."""
    response = create_po(client, auth_header(app, owner), supplier["id"])
    po = response.get_json()["purchaseOrder"]
    assert po["currency"] == "NGN"
    assert po["paymentTerms"] == "Net 30"


def test_an_explicit_currency_overrides_the_supplier_default(
    app, client, owner, supplier
):
    response = create_po(client, auth_header(app, owner), supplier["id"], currency="usd")
    assert response.get_json()["purchaseOrder"]["currency"] == "USD"


def test_a_nonsense_currency_is_refused(app, client, owner, supplier):
    response = create_po(client, auth_header(app, owner), supplier["id"], currency="dollars")
    assert response.status_code == 400
    assert "currency" in response.get_json()["fields"]


def test_a_new_order_starts_as_a_draft(app, client, owner, supplier):
    po = create_po(client, auth_header(app, owner), supplier["id"]).get_json()["purchaseOrder"]
    assert po["status"] == "draft"
    assert po["isEditable"] is True
    assert po["approvedAt"] is None


def test_the_creator_is_recorded(app, client, owner, supplier):
    po = create_po(client, auth_header(app, owner), supplier["id"]).get_json()["purchaseOrder"]
    assert po["createdBy"]["email"] == "owner@example.com"


def test_cost_attribution_fields_round_trip(app, client, owner, supplier):
    """Carried now because P2.5 routes approvals by them."""
    po = create_po(
        client, auth_header(app, owner), supplier["id"],
        department="Operations", costCenter="CC-12", project="Rig 4",
        category="Consumables", reference="REQ-88",
        expectedDeliveryDate="2026-12-15", deliveryAddress="Warehouse 2",
    ).get_json()["purchaseOrder"]

    assert po["department"] == "Operations"
    assert po["costCenter"] == "CC-12"
    assert po["project"] == "Rig 4"
    assert po["category"] == "Consumables"
    assert po["reference"] == "REQ-88"
    assert po["expectedDeliveryDate"] == "2026-12-15"
    assert po["deliveryAddress"] == "Warehouse 2"


def test_the_order_does_not_embed_supplier_bank_details(app, client, owner, supplier):
    """Embedding them would route around suppliers:bank:read, which is the one
    permission protecting the invoice-redirection fraud path."""
    po = create_po(client, auth_header(app, owner), supplier["id"]).get_json()["purchaseOrder"]
    assert "bankDetails" not in po["supplier"]


# ─── Editing ─────────────────────────────────────────────────────────────────
def test_a_draft_can_be_edited(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]

    response = client.patch(
        f"/api/purchase-orders/{po_id}",
        json={"notes": "Rush order", "lines": [{**LINE, "quantity": "6"}]},
        headers=headers,
    )
    assert response.status_code == 200
    po = response.get_json()["purchaseOrder"]
    assert po["notes"] == "Rush order"
    assert po["total"] == "645.00"      # 6 x 100 + 7.5%


def test_editing_lines_recomputes_the_stored_totals(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]
    client.patch(f"/api/purchase-orders/{po_id}",
                 json={"lines": [{**LINE, "quantity": "1", "taxRate": "0"}]},
                 headers=headers)

    with app.app_context():
        from models import PurchaseOrder
        row = PurchaseOrder.query.get(po_id)
        assert row.total == Decimal("100.0000")
        assert row.tax_total == Decimal("0.0000")


def test_an_approved_order_cannot_be_edited(app, client, owner, supplier):
    """Approval approves specific amounts. Editing afterwards would make the
    approval a signature on a document that no longer exists."""
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]
    assert approve_chain(client, headers, po_id).status_code == 200

    response = client.patch(f"/api/purchase-orders/{po_id}",
                            json={"lines": [{**LINE, "quantity": "1000"}]},
                            headers=headers)
    assert response.status_code == 409
    assert response.get_json()["code"] == "NOT_EDITABLE"

    # And the figures are untouched.
    after = client.get(f"/api/purchase-orders/{po_id}", headers=headers).get_json()
    assert after["purchaseOrder"]["total"] == "322.50"


def test_an_order_under_approval_cannot_be_edited_either(app, client, owner, supplier):
    """Otherwise the approver reviews one set of numbers and authorizes another."""
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]
    client.post(f"/api/purchase-orders/{po_id}/submit", headers=headers)

    response = client.patch(f"/api/purchase-orders/{po_id}",
                            json={"notes": "sneak"}, headers=headers)
    assert response.status_code == 409


def test_a_rejected_edit_leaves_nothing_half_applied(app, client, owner, supplier):
    """One bad line must not commit the good fields alongside it."""
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]

    response = client.patch(
        f"/api/purchase-orders/{po_id}",
        json={"notes": "should not stick", "lines": [{**LINE, "quantity": "-5"}]},
        headers=headers,
    )
    assert response.status_code == 400

    after = client.get(f"/api/purchase-orders/{po_id}", headers=headers).get_json()
    assert after["purchaseOrder"]["notes"] is None
    assert after["purchaseOrder"]["total"] == "322.50"


def test_an_edit_can_change_the_supplier_while_still_a_draft(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]
    other = make_supplier(app, owner["organization_id"], name="Beta Supplies")

    response = client.patch(f"/api/purchase-orders/{po_id}",
                            json={"supplierId": other["id"]}, headers=headers)
    assert response.status_code == 200
    assert response.get_json()["purchaseOrder"]["supplierId"] == other["id"]


def test_an_edit_cannot_move_the_order_to_another_organizations_supplier(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]
    stranger = make_user(app, email="s2@example.com", plan="pro")
    foreign = make_supplier(app, stranger["organization_id"], name="Foreign Two")

    response = client.patch(f"/api/purchase-orders/{po_id}",
                            json={"supplierId": foreign["id"]}, headers=headers)
    assert response.status_code == 400


# ─── Lifecycle ───────────────────────────────────────────────────────────────
def test_submit_moves_a_draft_to_pending_approval(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]

    response = client.post(f"/api/purchase-orders/{po_id}/submit", headers=headers)
    assert response.status_code == 200
    po = response.get_json()["purchaseOrder"]
    assert po["status"] == "pending_approval"
    assert po["submittedAt"] is not None


def test_an_empty_order_cannot_be_submitted(app, client, owner, supplier):
    """Nothing was ordered, so there is nothing to approve."""
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"],
                      lines=[]).get_json()["purchaseOrder"]["id"]

    response = client.post(f"/api/purchase-orders/{po_id}/submit", headers=headers)
    assert response.status_code == 409
    assert response.get_json()["code"] == "NO_LINES"


def test_approval_records_who_approved_and_when(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]
    po = approve_chain(client, headers, po_id).get_json()["purchaseOrder"]

    assert po["status"] == "approved"
    assert po["approvedAt"] is not None
    assert po["approvedBy"]["email"] == "owner@example.com"
    assert po["isEditable"] is False


def test_a_draft_cannot_be_approved_without_being_submitted(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]

    response = client.post(f"/api/purchase-orders/{po_id}/approve", headers=headers)
    assert response.status_code == 409
    assert response.get_json()["code"] == "INVALID_TRANSITION"


def test_rejection_sends_the_order_back_to_draft_with_a_reason(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]
    client.post(f"/api/purchase-orders/{po_id}/submit", headers=headers)

    response = client.post(f"/api/purchase-orders/{po_id}/reject",
                           json={"reason": "Over budget for Q4"}, headers=headers)
    assert response.status_code == 200
    po = response.get_json()["purchaseOrder"]
    assert po["status"] == "draft"
    assert po["rejectionReason"] == "Over budget for Q4"
    assert po["rejectedAt"] is not None
    assert po["isEditable"] is True


def test_a_rejection_must_say_why(app, client, owner, supplier):
    """A refusal with no reason leaves the person correcting the order nothing
    to act on, and no record of why money was refused."""
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]
    client.post(f"/api/purchase-orders/{po_id}/submit", headers=headers)

    response = client.post(f"/api/purchase-orders/{po_id}/reject",
                           json={"reason": "   "}, headers=headers)
    assert response.status_code == 400
    assert "reason" in response.get_json()["fields"]


def test_resubmitting_clears_the_previous_rejection(app, client, owner, supplier):
    """Leaving it would show an old rejection against an order now awaiting a
    fresh decision."""
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]
    client.post(f"/api/purchase-orders/{po_id}/submit", headers=headers)
    client.post(f"/api/purchase-orders/{po_id}/reject",
                json={"reason": "Too expensive"}, headers=headers)

    po = client.post(f"/api/purchase-orders/{po_id}/submit",
                     headers=headers).get_json()["purchaseOrder"]
    assert po["status"] == "pending_approval"
    assert po["rejectionReason"] is None
    assert po["rejectedAt"] is None


def test_an_approved_order_can_be_sent_then_received_then_closed(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]
    approve_chain(client, headers, po_id)

    for status in ("sent", "partially_received", "fully_received", "closed"):
        response = client.post(f"/api/purchase-orders/{po_id}/status",
                               json={"status": status}, headers=headers)
        assert response.status_code == 200, (status, response.get_json())
        assert response.get_json()["purchaseOrder"]["status"] == status


def test_a_draft_cannot_jump_straight_to_received(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]

    response = client.post(f"/api/purchase-orders/{po_id}/status",
                           json={"status": "fully_received"}, headers=headers)
    assert response.status_code == 409
    assert response.get_json()["code"] == "INVALID_TRANSITION"


def test_the_status_endpoint_cannot_be_used_to_approve(app, client, owner, supplier):
    """Otherwise purchase_orders:write would quietly grant approval."""
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]
    client.post(f"/api/purchase-orders/{po_id}/submit", headers=headers)

    response = client.post(f"/api/purchase-orders/{po_id}/status",
                           json={"status": "approved"}, headers=headers)
    assert response.status_code == 400
    assert response.get_json()["code"] == "WRONG_ENDPOINT"


def test_an_unknown_status_is_refused(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]

    response = client.post(f"/api/purchase-orders/{po_id}/status",
                           json={"status": "paid_in_bitcoin"}, headers=headers)
    assert response.status_code == 409
    assert response.get_json()["code"] == "UNKNOWN_STATUS"


def test_an_order_is_cancelled_never_deleted(app, client, owner, supplier):
    """An order that was approved is a record of a commitment. Abandoning it
    does not make that untrue, and an invoice may still arrive against it."""
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]

    response = client.delete(f"/api/purchase-orders/{po_id}", headers=headers)
    assert response.status_code == 200
    assert response.get_json()["purchaseOrder"]["status"] == "cancelled"

    # Still there, still readable.
    assert client.get(f"/api/purchase-orders/{po_id}",
                      headers=headers).status_code == 200


def test_a_cancelled_order_is_terminal(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]
    client.delete(f"/api/purchase-orders/{po_id}", headers=headers)

    assert client.post(f"/api/purchase-orders/{po_id}/submit",
                       headers=headers).status_code == 409
    assert client.patch(f"/api/purchase-orders/{po_id}", json={"notes": "x"},
                        headers=headers).status_code == 409
    assert client.delete(f"/api/purchase-orders/{po_id}",
                         headers=headers).status_code == 409


def test_a_closed_order_is_terminal(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]
    approve_chain(client, headers, po_id)
    for status in ("sent", "fully_received", "closed"):
        client.post(f"/api/purchase-orders/{po_id}/status",
                    json={"status": status}, headers=headers)

    response = client.post(f"/api/purchase-orders/{po_id}/status",
                           json={"status": "cancelled"}, headers=headers)
    assert response.status_code == 409


def test_restating_the_current_status_is_a_no_change_not_a_silent_success(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]
    client.post(f"/api/purchase-orders/{po_id}/submit", headers=headers)

    response = client.post(f"/api/purchase-orders/{po_id}/submit", headers=headers)
    assert response.status_code == 409
    assert response.get_json()["code"] == "NO_CHANGE"


def test_the_detail_payload_advertises_the_legal_next_moves(app, client, owner, supplier):
    """So the client greys out buttons from the server's rules rather than
    keeping its own copy of the lifecycle, which would drift."""
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]
    assert po["nextStatuses"] == ["cancelled", "pending_approval"]


# ─── Segregation of duties ───────────────────────────────────────────────────
def test_a_solo_user_can_approve_their_own_order(app, client, owner, supplier):
    """Refusing here would make approval impossible rather than safer."""
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]
    response = approve_chain(client, headers, po_id)
    assert response.status_code == 200
    assert response.get_json()["purchaseOrder"]["status"] == "approved"


def test_you_cannot_approve_your_own_order_where_another_approver_exists(app, client):
    """Raising and authorizing the same commitment is the classic
    internal-control failure. A product that exists to impose financial
    discipline should not be where it happens."""
    boss = make_user(app, email="boss@example.com", plan="pro")
    org = make_org(app, boss, name="Team Co", plan="pro")
    colleague = make_user(app, email="colleague@example.com", plan="pro")
    join_org(app, org, colleague, FINANCE_MANAGER)
    vendor = make_supplier(app, org["id"], name="Team Vendor")

    boss_headers = org_header(app, boss, org)
    po_id = create_po(client, boss_headers, vendor["id"]).get_json()["purchaseOrder"]["id"]
    client.post(f"/api/purchase-orders/{po_id}/submit", headers=boss_headers)

    refused = client.post(f"/api/purchase-orders/{po_id}/approve", headers=boss_headers)
    assert refused.status_code == 409
    assert refused.get_json()["code"] == "SELF_APPROVAL"

    # The colleague can.
    accepted = client.post(f"/api/purchase-orders/{po_id}/approve",
                           headers=org_header(app, colleague, org))
    assert accepted.status_code == 200
    assert accepted.get_json()["purchaseOrder"]["approvedBy"]["email"] == \
        "colleague@example.com"


def test_a_colleague_who_cannot_approve_does_not_count_as_a_second_approver(app, client):
    """The rule counts members who hold approvals:act, not members. An
    organization of one approver and five viewers still has one approver."""
    boss = make_user(app, email="boss2@example.com", plan="pro")
    org = make_org(app, boss, name="Viewers Co", plan="pro")
    join_org(app, org, make_user(app, email="v1@example.com", plan="pro"), VIEWER)
    join_org(app, org, make_user(app, email="v2@example.com", plan="pro"), ACCOUNTANT)
    vendor = make_supplier(app, org["id"], name="Solo Vendor")

    headers = org_header(app, boss, org)
    po_id = create_po(client, headers, vendor["id"]).get_json()["purchaseOrder"]["id"]
    assert approve_chain(client, headers, po_id).status_code == 200


def test_someone_else_raising_the_order_can_always_be_approved(app, client):
    buyer = make_user(app, email="buyer@example.com", plan="pro")
    org = make_org(app, buyer, name="Split Co", plan="pro")
    officer = make_user(app, email="officer@example.com", plan="pro")
    join_org(app, org, officer, PROCUREMENT)
    vendor = make_supplier(app, org["id"], name="Split Vendor")

    officer_headers = org_header(app, officer, org)
    po_id = create_po(client, officer_headers,
                      vendor["id"]).get_json()["purchaseOrder"]["id"]
    client.post(f"/api/purchase-orders/{po_id}/submit", headers=officer_headers)

    response = client.post(f"/api/purchase-orders/{po_id}/approve",
                           headers=org_header(app, buyer, org))
    assert response.status_code == 200


# ─── Permissions ─────────────────────────────────────────────────────────────
def test_a_viewer_can_read_but_not_create(app, client, owner, supplier):
    viewer = make_user(app, email="viewer@example.com", plan="pro")
    org = make_org(app, owner, name="Perm Co", plan="pro")
    join_org(app, org, viewer, VIEWER)
    vendor = make_supplier(app, org["id"], name="Perm Vendor")
    create_po(client, org_header(app, owner, org), vendor["id"])

    headers = org_header(app, viewer, org)
    assert client.get("/api/purchase-orders", headers=headers).status_code == 200
    assert create_po(client, headers, vendor["id"]).status_code == 403


def test_an_accountant_cannot_raise_a_purchase_order(app, client, owner):
    """Accountants record what happened; they do not commit the organization to
    spending. purchase_orders:write is a procurement capability."""
    accountant = make_user(app, email="acct@example.com", plan="pro")
    org = make_org(app, owner, name="Acct Co", plan="pro")
    join_org(app, org, accountant, ACCOUNTANT)
    vendor = make_supplier(app, org["id"], name="Acct Vendor")

    assert create_po(client, org_header(app, accountant, org),
                     vendor["id"]).status_code == 403


def test_a_procurement_officer_can_raise_but_not_approve(app, client, owner):
    officer = make_user(app, email="proc@example.com", plan="pro")
    org = make_org(app, owner, name="Proc Co", plan="pro")
    join_org(app, org, officer, PROCUREMENT)
    vendor = make_supplier(app, org["id"], name="Proc Vendor")

    headers = org_header(app, officer, org)
    po_id = create_po(client, headers, vendor["id"]).get_json()["purchaseOrder"]["id"]
    client.post(f"/api/purchase-orders/{po_id}/submit", headers=headers)

    assert client.post(f"/api/purchase-orders/{po_id}/approve",
                       headers=headers).status_code == 403


def test_an_approver_can_approve_but_not_raise(app, client, owner):
    approver = make_user(app, email="appr@example.com", plan="pro")
    org = make_org(app, owner, name="Appr Co", plan="pro")
    join_org(app, org, approver, APPROVER)
    vendor = make_supplier(app, org["id"], name="Appr Vendor")

    owner_headers = org_header(app, owner, org)
    po_id = create_po(client, owner_headers, vendor["id"]).get_json()["purchaseOrder"]["id"]
    client.post(f"/api/purchase-orders/{po_id}/submit", headers=owner_headers)

    approver_headers = org_header(app, approver, org)
    assert create_po(client, approver_headers, vendor["id"]).status_code == 403
    assert client.post(f"/api/purchase-orders/{po_id}/approve",
                       headers=approver_headers).status_code == 200


def test_purchase_orders_require_authentication(client):
    assert client.get("/api/purchase-orders").status_code == 401
    assert client.post("/api/purchase-orders", json={}).status_code == 401


# ─── Tenancy ─────────────────────────────────────────────────────────────────
def test_one_organization_cannot_read_anothers_orders(app, client, owner, supplier):
    po_id = create_po(client, auth_header(app, owner),
                      supplier["id"]).get_json()["purchaseOrder"]["id"]
    stranger = make_user(app, email="nosy@example.com", plan="pro")
    headers = auth_header(app, stranger)

    assert client.get(f"/api/purchase-orders/{po_id}", headers=headers).status_code == 404
    assert client.patch(f"/api/purchase-orders/{po_id}", json={"notes": "x"},
                        headers=headers).status_code == 404
    assert client.delete(f"/api/purchase-orders/{po_id}",
                         headers=headers).status_code == 404
    assert client.post(f"/api/purchase-orders/{po_id}/submit",
                       headers=headers).status_code == 404
    assert client.get(f"/api/purchase-orders/{po_id}/pdf",
                      headers=headers).status_code == 404


def test_the_list_shows_only_the_callers_organization(app, client, owner, supplier):
    create_po(client, auth_header(app, owner), supplier["id"])
    stranger = make_user(app, email="other@example.com", plan="pro")
    other_vendor = make_supplier(app, stranger["organization_id"], name="Theirs")
    create_po(client, auth_header(app, stranger), other_vendor["id"])

    body = client.get("/api/purchase-orders", headers=auth_header(app, owner)).get_json()
    assert body["total"] == 1
    assert body["purchaseOrders"][0]["supplierName"] == "Acme Supplies Ltd"


def test_switching_organization_switches_the_orders(app, client, owner, supplier):
    other = make_org(app, owner, name="Second", plan="pro")
    other_vendor = make_supplier(app, other["id"], name="Second Vendor")
    create_po(client, auth_header(app, owner), supplier["id"])
    create_po(client, org_header(app, owner, other), other_vendor["id"])

    personal = client.get("/api/purchase-orders",
                          headers=auth_header(app, owner)).get_json()
    shared = client.get("/api/purchase-orders",
                        headers=org_header(app, owner, other)).get_json()
    assert personal["total"] == 1
    assert shared["total"] == 1
    assert personal["purchaseOrders"][0]["id"] != shared["purchaseOrders"][0]["id"]


# ─── List, filter, summary ───────────────────────────────────────────────────
def test_the_list_filters_by_status(app, client, owner, supplier):
    headers = auth_header(app, owner)
    first = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]
    create_po(client, headers, supplier["id"])
    client.post(f"/api/purchase-orders/{first}/submit", headers=headers)

    body = client.get("/api/purchase-orders?status=pending_approval",
                      headers=headers).get_json()
    assert body["total"] == 1
    assert body["purchaseOrders"][0]["id"] == first


def test_the_list_filters_by_supplier(app, client, owner, supplier):
    headers = auth_header(app, owner)
    other = make_supplier(app, owner["organization_id"], name="Gamma Ltd")
    create_po(client, headers, supplier["id"])
    create_po(client, headers, other["id"])

    body = client.get(f"/api/purchase-orders?supplierId={other['id']}",
                      headers=headers).get_json()
    assert body["total"] == 1
    assert body["purchaseOrders"][0]["supplierName"] == "Gamma Ltd"


def test_the_list_searches_number_and_reference(app, client, owner, supplier):
    headers = auth_header(app, owner)
    create_po(client, headers, supplier["id"], reference="REQ-2026-77")
    create_po(client, headers, supplier["id"], reference="OTHER")

    assert client.get("/api/purchase-orders?q=2026-77",
                      headers=headers).get_json()["total"] == 1
    assert client.get("/api/purchase-orders?q=PO-0001",
                      headers=headers).get_json()["total"] == 1


def test_the_open_filter_covers_the_states_that_still_commit_money(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    approved = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]
    approve_chain(client, headers, approved)
    create_po(client, headers, supplier["id"])              # a draft, not open

    body = client.get("/api/purchase-orders?status=open", headers=headers).get_json()
    assert [po["id"] for po in body["purchaseOrders"]] == [approved]


def test_the_list_paginates(app, client, owner, supplier):
    headers = auth_header(app, owner)
    for _ in range(5):
        create_po(client, headers, supplier["id"])

    body = client.get("/api/purchase-orders?perPage=2&page=2", headers=headers).get_json()
    assert body["total"] == 5
    assert body["pages"] == 3
    assert len(body["purchaseOrders"]) == 2


def test_the_summary_reports_open_commitment_per_currency(app, client, owner, supplier):
    """Never summed across currencies: one figure spanning USD and NGN is a
    meaningless number that looks authoritative."""
    headers = auth_header(app, owner)
    usd_vendor = make_supplier(app, owner["organization_id"], name="Dollar Co",
                               currency="USD")

    ngn = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]
    usd = create_po(client, headers, usd_vendor["id"]).get_json()["purchaseOrder"]["id"]
    approve_chain(client, headers, ngn)
    approve_chain(client, headers, usd)
    create_po(client, headers, supplier["id"])              # draft: not committed

    body = client.get("/api/purchase-orders/summary", headers=headers).get_json()
    by_currency = {row["currency"]: row for row in body["openCommitment"]}
    assert by_currency["NGN"]["total"] == "322.50"
    assert by_currency["USD"]["total"] == "322.50"
    assert set(by_currency) == {"NGN", "USD"}
    assert body["counts"]["draft"] == 1
    assert body["counts"]["approved"] == 2


def test_the_summary_counts_what_is_waiting_on_someone(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]
    client.post(f"/api/purchase-orders/{po_id}/submit", headers=headers)

    body = client.get("/api/purchase-orders/summary", headers=headers).get_json()
    assert body["awaitingApproval"] == 1


def test_a_missing_order_is_a_404_not_a_500(app, client, owner):
    assert client.get("/api/purchase-orders/nope",
                      headers=auth_header(app, owner)).status_code == 404


# ─── Attachments ─────────────────────────────────────────────────────────────
def upload(client, headers, po_id, name="quote.pdf", data=b"%PDF-1.4 fake",
           mime="application/pdf"):
    import io

    return client.post(
        f"/api/purchase-orders/{po_id}/attachments",
        data={"file": (io.BytesIO(data), name, mime)},
        content_type="multipart/form-data",
        headers=headers,
    )


def test_an_attachment_is_stored_and_listed(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]

    response = upload(client, headers, po_id)
    assert response.status_code == 201
    assert response.get_json()["attachment"]["fileName"] == "quote.pdf"

    detail = client.get(f"/api/purchase-orders/{po_id}", headers=headers).get_json()
    assert len(detail["purchaseOrder"]["attachments"]) == 1


def test_an_attachment_can_be_downloaded_back(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]
    attachment_id = upload(client, headers, po_id,
                           data=b"%PDF-1.4 hello").get_json()["attachment"]["id"]

    response = client.get(
        f"/api/purchase-orders/{po_id}/attachments/{attachment_id}", headers=headers
    )
    assert response.status_code == 200
    assert response.data == b"%PDF-1.4 hello"


def test_attachments_stay_addable_after_approval(app, client, owner, supplier):
    """Evidence about the order, not a term of it, so adding one cannot change
    what was agreed."""
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]
    approve_chain(client, headers, po_id)

    assert upload(client, headers, po_id, name="signed.pdf").status_code == 201


def test_a_cancelled_order_takes_no_more_attachments(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]
    client.delete(f"/api/purchase-orders/{po_id}", headers=headers)

    assert upload(client, headers, po_id).status_code == 409


def test_a_filename_cannot_escape_the_upload_directory(app, client, owner, supplier):
    """The client's filename never reaches the path: it is sanitized and
    prefixed with the attachment id."""
    import os

    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]
    response = upload(client, headers, po_id, name="../../../../etc/passwd.pdf")
    assert response.status_code == 201

    with app.app_context():
        from config import Config
        from models import PurchaseOrderAttachment

        row = PurchaseOrderAttachment.query.filter_by(purchase_order_id=po_id).one()
        assert ".." not in row.stored_name
        assert "/" not in row.stored_name and "\\" not in row.stored_name
        expected = os.path.join(Config.UPLOAD_DIR, "po", po_id, row.stored_name)
        assert os.path.isfile(expected)


def test_an_unacceptable_file_type_is_refused(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]

    response = upload(client, headers, po_id, name="run.exe", data=b"MZ",
                      mime="application/x-msdownload")
    assert response.status_code == 415


def test_an_empty_file_is_refused(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]

    assert upload(client, headers, po_id, data=b"").status_code == 400


def test_a_request_with_no_file_is_refused(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]

    response = client.post(f"/api/purchase-orders/{po_id}/attachments",
                           data={}, content_type="multipart/form-data",
                           headers=headers)
    assert response.status_code == 400


def test_another_organization_cannot_download_an_attachment(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]
    attachment_id = upload(client, headers, po_id).get_json()["attachment"]["id"]

    stranger = auth_header(app, make_user(app, email="thief@example.com", plan="pro"))
    assert client.get(f"/api/purchase-orders/{po_id}/attachments/{attachment_id}",
                      headers=stranger).status_code == 404


def test_an_attachment_from_another_order_is_not_served(app, client, owner, supplier):
    headers = auth_header(app, owner)
    first = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]
    second = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]
    attachment_id = upload(client, headers, first).get_json()["attachment"]["id"]

    assert client.get(f"/api/purchase-orders/{second}/attachments/{attachment_id}",
                      headers=headers).status_code == 404


def test_an_attachment_can_be_removed(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]
    attachment_id = upload(client, headers, po_id).get_json()["attachment"]["id"]

    assert client.delete(f"/api/purchase-orders/{po_id}/attachments/{attachment_id}",
                         headers=headers).status_code == 200
    detail = client.get(f"/api/purchase-orders/{po_id}", headers=headers).get_json()
    assert detail["purchaseOrder"]["attachments"] == []


def test_attachments_are_capped(app, client, owner, supplier):
    from routes.purchase_order_routes import MAX_ATTACHMENTS

    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]
    for index in range(MAX_ATTACHMENTS):
        assert upload(client, headers, po_id, name=f"f{index}.pdf").status_code == 201

    assert upload(client, headers, po_id, name="one-too-many.pdf").status_code == 400


# ─── PDF ─────────────────────────────────────────────────────────────────────
def test_the_order_renders_as_a_pdf(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po_id = create_po(
        client, headers, supplier["id"],
        lines=[{**LINE, "description": "Widget", "sku": "W-1", "unit": "each"},
               {**LINE, "description": "Bolt", "quantity": "250",
                "unitPrice": "0.45", "taxRate": "0"}],
        notes="Deliver to gate 3.", deliveryAddress="Yard B\nPort Harcourt",
    ).get_json()["purchaseOrder"]["id"]

    response = client.get(f"/api/purchase-orders/{po_id}/pdf", headers=headers)
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF-")
    assert response.data.rstrip().endswith(b"%%EOF")
    assert len(response.data) > 1500
    assert "attachment;" in response.headers["Content-Disposition"]
    assert "PO-0001.pdf" in response.headers["Content-Disposition"]


def test_a_pdf_of_an_empty_order_still_renders(app, client, owner, supplier):
    """A draft with no lines is a normal thing to print while working on it."""
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"],
                      lines=[]).get_json()["purchaseOrder"]["id"]

    response = client.get(f"/api/purchase-orders/{po_id}/pdf", headers=headers)
    assert response.status_code == 200
    assert response.data.startswith(b"%PDF-")


def test_markup_in_a_description_cannot_break_the_pdf(app, client, owner, supplier):
    """reportlab parses its own tag subset, so an unescaped '<' would either
    swallow the text or abort the whole render."""
    headers = auth_header(app, owner)
    po_id = create_po(
        client, headers, supplier["id"],
        lines=[{**LINE, "description": "<b>Bracket & <unclosed tag"}],
        notes="A & B <notes>",
    ).get_json()["purchaseOrder"]["id"]

    response = client.get(f"/api/purchase-orders/{po_id}/pdf", headers=headers)
    assert response.status_code == 200
    assert response.data.startswith(b"%PDF-")


def test_an_unapproved_order_is_labelled_as_no_authorization_to_supply(app):
    """Printing a draft that reads as approved is how an unapproved commitment
    becomes a real one."""
    with app.app_context():
        from po_pdf import STATUS_LABELS, UNAUTHORIZED

        assert "NOT YET APPROVED" in STATUS_LABELS["draft"]
        assert "NOT YET APPROVED" in STATUS_LABELS["pending_approval"]
        assert {"draft", "pending_approval", "cancelled"} == UNAUTHORIZED
        assert "approved" not in UNAUTHORIZED
        assert "sent" not in UNAUTHORIZED


def test_the_pdf_escapes_the_markup_characters_that_matter(app):
    with app.app_context():
        from po_pdf import _esc

        assert _esc("a & b") == "a &amp; b"
        assert _esc("<b>x</b>") == "&lt;b&gt;x&lt;/b&gt;"
        assert _esc(None) == ""


def test_quantities_print_without_trailing_zeros(app):
    """The unit column carries the meaning; the zeros carry nothing."""
    with app.app_context():
        from po_pdf import _qty

        assert _qty(Decimal("3.0000")) == "3"
        assert _qty(Decimal("2.5000")) == "2.5"
        assert _qty(Decimal("300.0000")) == "300"      # not 3E+2
        assert _qty(None) == "-"


def test_a_pdf_request_without_the_renderer_fails_clearly(app, client, owner, supplier,
                                                          monkeypatch):
    """A server that has not been rebuilt since this landed should say so, not
    serve a 500 traceback."""
    headers = auth_header(app, owner)
    po_id = create_po(client, headers, supplier["id"]).get_json()["purchaseOrder"]["id"]

    import po_pdf
    monkeypatch.setattr(po_pdf, "REPORTLAB_AVAILABLE", False)

    response = client.get(f"/api/purchase-orders/{po_id}/pdf", headers=headers)
    assert response.status_code == 503
    assert response.get_json()["code"] == "PDF_UNAVAILABLE"


# ─── Lifecycle rules as a unit ───────────────────────────────────────────────
def test_every_status_has_a_declared_transition_set(app):
    """A status with no entry would be a dead end nothing can leave, which is
    only correct for the two terminal ones."""
    with app.app_context():
        from models import PurchaseOrder

        assert set(PurchaseOrder.TRANSITIONS) == set(PurchaseOrder.STATUSES)
        terminal = {status for status, nxt in PurchaseOrder.TRANSITIONS.items() if not nxt}
        assert terminal == {PurchaseOrder.CLOSED, PurchaseOrder.CANCELLED}


def test_no_transition_points_at_a_status_that_does_not_exist(app):
    with app.app_context():
        from models import PurchaseOrder

        for status, allowed in PurchaseOrder.TRANSITIONS.items():
            unknown = allowed - set(PurchaseOrder.STATUSES)
            assert not unknown, f"{status} -> {unknown}"


def test_only_a_draft_is_editable(app):
    with app.app_context():
        from models import PurchaseOrder

        assert {PurchaseOrder.DRAFT} == PurchaseOrder.EDITABLE_STATUSES


def test_the_line_amounts_foot_to_the_subtotal(app, client, owner, supplier):
    """The invariant the PDF and the UI both present.

    The per-line amount column is the NET amount, so it adds up to Subtotal,
    and Subtotal + Tax = Total. Showing tax-inclusive line amounts above a
    "Subtotal" label makes a document whose own columns disagree - which is the
    first thing anyone checking it will notice.
    """
    lines = [
        {"description": "A", "quantity": "12", "unitPrice": "18500.00", "taxRate": "7.5"},
        {"description": "B", "quantity": "8", "unitPrice": "23400.50", "taxRate": "7.5"},
        {"description": "C", "quantity": "2.5", "unitPrice": "46000.00", "taxRate": "7.5"},
        {"description": "D", "quantity": "1", "unitPrice": "92750.00", "taxRate": "0"},
    ]
    po = create_po(client, auth_header(app, owner), supplier["id"],
                   lines=lines).get_json()["purchaseOrder"]

    net = sum(Decimal(line["lineSubtotal"]) for line in po["lines"])
    tax = sum(Decimal(line["taxAmount"]) for line in po["lines"])
    gross = sum(Decimal(line["lineTotal"]) for line in po["lines"])

    assert net == Decimal(po["subtotal"]) == Decimal("616954.00")
    assert tax == Decimal(po["taxTotal"]) == Decimal("39315.30")
    assert gross == Decimal(po["total"]) == Decimal("656269.30")
    assert Decimal(po["subtotal"]) + Decimal(po["taxTotal"]) == Decimal(po["total"])


def test_a_cancelled_order_is_not_footed_as_approved(app):
    """An approved order that was later cancelled still has an approval date.
    Leading the PDF footer with it would be true and badly misleading."""
    with app.app_context():
        from po_pdf import UNAUTHORIZED

        assert "cancelled" in UNAUTHORIZED


def test_the_open_commitment_total_survives_amounts_a_float_would_mangle(
    app, client, owner, supplier
):
    """The aggregate is summed as Decimal, not float.

    0.1 + 0.2 != 0.3 in binary floating point, and a commitment figure is a
    number people act on. Three lines that a float would total to
    0.30000000000000004 must come back as exactly 0.30.
    """
    headers = auth_header(app, owner)
    lines = [
        {"description": "a", "quantity": "1", "unitPrice": "0.10", "taxRate": "0"},
        {"description": "b", "quantity": "1", "unitPrice": "0.20", "taxRate": "0"},
    ]
    first = create_po(client, headers, supplier["id"],
                      lines=lines).get_json()["purchaseOrder"]["id"]
    approve_chain(client, headers, first)

    body = client.get("/api/purchase-orders/summary", headers=headers).get_json()
    ngn = next(row for row in body["openCommitment"] if row["currency"] == "NGN")
    assert ngn["total"] == "0.30"
    assert Decimal(ngn["total"]) == Decimal("0.30")


def test_a_large_commitment_total_is_exact(app, client, owner, supplier):
    """Beyond 2^53 a float silently drops cents. These figures are stored and
    summed as Decimal all the way through."""
    headers = auth_header(app, owner)
    for _ in range(3):
        po_id = create_po(
            client, headers, supplier["id"],
            lines=[{"description": "bulk", "quantity": "1",
                    "unitPrice": "9007199254740.99", "taxRate": "0"}],
        ).get_json()["purchaseOrder"]["id"]
        approve_chain(client, headers, po_id)

    body = client.get("/api/purchase-orders/summary", headers=headers).get_json()
    ngn = next(row for row in body["openCommitment"] if row["currency"] == "NGN")
    assert ngn["total"] == "27021597764222.97"
