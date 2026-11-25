"""Goods receipts and three-way matching (P2.4).

The leg that stops an organization paying for goods that never arrived. These
tests lean hardest on the four places that decision can go wrong:

* **accepted, not received.** Damaged and rejected goods are delivered and not
  owed for. A system that pays on "it turned up" pays for broken stock.
* **posted, not drafted.** A half-entered delivery note must not make an
  invoice payable.
* **recomputed, not incremented.** Cancel a receipt and the quantities must go
  back, or the order's position quietly drifts away from its paperwork.
* **off until it is used.** Three-way matching must not block every invoice in
  an organization that does not record deliveries.

Every fixture runs on the **Pro** plan: payables is a Pro capability
(`plans.PAYABLES`), and below it every endpoint here answers 402.
"""
import io
from decimal import Decimal

import pytest

from invoice_schema import normalize
from roles import ACCOUNTANT, ADMIN, PROCUREMENT, VIEWER
from tests.conftest import auth_header, join_org, make_org, make_user, org_header


# ─── Fixtures and helpers ────────────────────────────────────────────────────
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


PO_LINE = {"description": "Hydraulic hose", "sku": "HH-1003", "unit": "each",
           "quantity": "10", "unitPrice": "100.00", "taxRate": "0"}


def create_po(client, headers, supplier_id, lines=None, approve=True, **extra):
    body = {"supplierId": supplier_id, "lines": lines if lines is not None else [PO_LINE]}
    body.update(extra)
    response = client.post("/api/purchase-orders", json=body, headers=headers)
    assert response.status_code == 201, response.get_json()
    po = response.get_json()["purchaseOrder"]
    if approve:
        client.post(f"/api/purchase-orders/{po['id']}/submit", headers=headers)
        approved = client.post(f"/api/purchase-orders/{po['id']}/approve",
                               headers=headers)
        assert approved.status_code == 200, approved.get_json()
        po = approved.get_json()["purchaseOrder"]
    return po


def po_lines(client, headers, po_id):
    body = client.get(f"/api/purchase-orders/{po_id}", headers=headers).get_json()
    return body["purchaseOrder"]["lines"]


def receipt_line(po_line_id, received, damaged=0, rejected=0, notes=None):
    return {
        "purchaseOrderLineId": po_line_id,
        "quantityReceived": str(received),
        "quantityDamaged": str(damaged),
        "quantityRejected": str(rejected),
        "notes": notes,
    }


def create_grn(client, headers, po_id, lines, post=False, **extra):
    body = {"purchaseOrderId": po_id, "lines": lines}
    body.update(extra)
    response = client.post("/api/goods-receipts", json=body, headers=headers)
    assert response.status_code == 201, response.get_json()
    grn = response.get_json()["goodsReceipt"]
    if post:
        posted = client.post(f"/api/goods-receipts/{grn['id']}/post", headers=headers)
        assert posted.status_code == 200, posted.get_json()
        grn = posted.get_json()["goodsReceipt"]
    return grn


INVOICE_LINE = {"description": "Hydraulic hose", "product_name": "HH-1003",
                "quantity": 10, "unit_price": 100, "discount": None,
                "tax_rate": 0, "amount": 1000}


def invoice_doc(*, reference="PO-0001", lines=None, total="1000.00",
                number="INV-001"):
    return normalize({
        "vendor": {"name": "Acme Supplies Ltd"},
        "customer": {"name": "Us Ltd"},
        "invoice_number": number,
        "invoice_date": "2026-11-20",
        "currency": "NGN",
        "purchase_order_reference": reference,
        "line_items": lines if lines is not None else [dict(INVOICE_LINE)],
        "subtotal": total, "tax": 0, "total": total,
        "confidence": {},
    })


def make_invoice(app, owner, document, *, supplier_id=None, name="inv.pdf"):
    from documents import apply_headline_fields
    from extensions import db
    from models import Extraction

    with app.app_context():
        row = Extraction(
            organization_id=owner["organization_id"],
            user_id=owner["id"],
            doc_type="invoice",
            file_name=name,
            file_type="application/pdf",
            file_size=1024,
            supplier_id=supplier_id,
            data="{}",
            status="completed",
        )
        apply_headline_fields(row, document)
        db.session.add(row)
        db.session.commit()
        return row.id


def link(client, headers, eid, po_id):
    response = client.post(f"/api/matching/invoices/{eid}/link",
                           json={"purchaseOrderId": po_id}, headers=headers)
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def comparison_for(client, headers, eid):
    return client.get(f"/api/matching/invoices/{eid}",
                      headers=headers).get_json()["comparison"]


def codes(comparison):
    return [f["code"] for f in comparison["findings"]]


def by_code(comparison, code):
    return next(f for f in comparison["findings"] if f["code"] == code)


# ─── Accepted is what counts ─────────────────────────────────────────────────
def test_accepted_is_received_less_damaged_and_rejected(app):
    with app.app_context():
        from goods_receipts import compute_accepted

        assert compute_accepted("10", "1", "1") == Decimal("8.0000")
        assert compute_accepted("10", 0, 0) == Decimal("10.0000")
        assert compute_accepted("2.5", "0.5", 0) == Decimal("2.0000")


def test_accepted_never_goes_negative(app):
    """Belt and braces. The API refuses damaged + rejected above received, and
    a negative accepted would be subtracted from an order's position."""
    with app.app_context():
        from goods_receipts import compute_accepted

        assert compute_accepted("2", "5", "5") == Decimal("0")


def test_damaged_and_rejected_above_received_is_refused(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]

    response = client.post("/api/goods-receipts", json={
        "purchaseOrderId": po["id"],
        "lines": [receipt_line(line["id"], 5, damaged=4, rejected=4)],
    }, headers=headers)
    assert response.status_code == 400
    assert "lines.0.quantityDamaged" in response.get_json()["fields"]


def test_a_negative_quantity_is_refused(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]

    response = client.post("/api/goods-receipts", json={
        "purchaseOrderId": po["id"],
        "lines": [receipt_line(line["id"], -3)],
    }, headers=headers)
    assert response.status_code == 400
    assert "lines.0.quantityReceived" in response.get_json()["fields"]


def test_the_same_order_line_cannot_appear_twice_on_one_receipt(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]

    response = client.post("/api/goods-receipts", json={
        "purchaseOrderId": po["id"],
        "lines": [receipt_line(line["id"], 3), receipt_line(line["id"], 4)],
    }, headers=headers)
    assert response.status_code == 400
    assert "lines.1.purchaseOrderLineId" in response.get_json()["fields"]


def test_a_line_from_another_order_is_refused(app, client, owner, supplier):
    headers = auth_header(app, owner)
    first = create_po(client, headers, supplier["id"])
    second = create_po(client, headers, supplier["id"])
    other_line = po_lines(client, headers, second["id"])[0]

    response = client.post("/api/goods-receipts", json={
        "purchaseOrderId": first["id"],
        "lines": [receipt_line(other_line["id"], 3)],
    }, headers=headers)
    assert response.status_code == 400
    assert "lines.0.purchaseOrderLineId" in response.get_json()["fields"]


# ─── Posting ─────────────────────────────────────────────────────────────────
def test_a_draft_receipt_does_not_move_the_order(app, client, owner, supplier):
    """A half-entered delivery note must count for nothing."""
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]
    create_grn(client, headers, po["id"], [receipt_line(line["id"], 10)])

    after = po_lines(client, headers, po["id"])[0]
    assert after["quantityReceived"] == "0.00"
    assert after["quantityAccepted"] == "0.00"
    body = client.get(f"/api/purchase-orders/{po['id']}", headers=headers).get_json()
    assert body["purchaseOrder"]["status"] == "approved"


def test_posting_records_received_and_accepted_separately(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]
    create_grn(client, headers, po["id"],
               [receipt_line(line["id"], 10, damaged=1, rejected=1)], post=True)

    after = po_lines(client, headers, po["id"])[0]
    assert after["quantityReceived"] == "10.00"
    assert after["quantityAccepted"] == "8.00"


def test_a_receipt_with_nothing_received_cannot_be_posted(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]
    grn = create_grn(client, headers, po["id"], [receipt_line(line["id"], 0)])

    response = client.post(f"/api/goods-receipts/{grn['id']}/post", headers=headers)
    assert response.status_code == 409
    assert response.get_json()["code"] == "NOTHING_RECEIVED"


def test_a_posted_receipt_cannot_be_edited(app, client, owner, supplier):
    """Invoices have been measured against it."""
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]
    grn = create_grn(client, headers, po["id"], [receipt_line(line["id"], 5)],
                     post=True)

    response = client.patch(f"/api/goods-receipts/{grn['id']}",
                            json={"carrier": "DHL"}, headers=headers)
    assert response.status_code == 409
    assert response.get_json()["code"] == "NOT_EDITABLE"


def test_a_posted_receipt_cannot_go_back_to_draft(app, client, owner, supplier):
    with app.app_context():
        from models import GoodsReceipt

        assert GoodsReceipt.TRANSITIONS[GoodsReceipt.POSTED] == {
            GoodsReceipt.CANCELLED
        }


def test_a_draft_receipt_can_be_edited(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]
    grn = create_grn(client, headers, po["id"], [receipt_line(line["id"], 5)])

    response = client.patch(
        f"/api/goods-receipts/{grn['id']}",
        json={"carrier": "DHL", "deliveryNoteRef": "DN-99",
              "lines": [receipt_line(line["id"], 7)]},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.get_json()["goodsReceipt"]
    assert body["carrier"] == "DHL"
    assert body["lines"][0]["quantityReceived"] == "7.00"


# ─── The order's status follows the goods ────────────────────────────────────
def test_a_partial_delivery_moves_the_order_to_partially_received(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]
    create_grn(client, headers, po["id"], [receipt_line(line["id"], 4)], post=True)

    body = client.get(f"/api/purchase-orders/{po['id']}", headers=headers).get_json()
    assert body["purchaseOrder"]["status"] == "partially_received"


def test_a_full_delivery_moves_the_order_to_fully_received(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]
    create_grn(client, headers, po["id"], [receipt_line(line["id"], 10)], post=True)

    body = client.get(f"/api/purchase-orders/{po['id']}", headers=headers).get_json()
    assert body["purchaseOrder"]["status"] == "fully_received"


def test_damaged_goods_do_not_complete_an_order(app, client, owner, supplier):
    """Ten arrived, two broken. The supplier still owes two, so the order is
    not finished — counting damaged stock toward completion would close it."""
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]
    create_grn(client, headers, po["id"],
               [receipt_line(line["id"], 10, damaged=2)], post=True)

    body = client.get(f"/api/purchase-orders/{po['id']}", headers=headers).get_json()
    assert body["purchaseOrder"]["status"] == "partially_received"


def test_an_approved_order_can_receive_without_being_marked_sent(
    app, client, owner, supplier
):
    """Goods arriving is proof the order reached the supplier. Refusing the
    delivery because nobody pressed "sent" would make the paperwork argue with
    the loading dock."""
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    assert po["status"] == "approved"
    line = po_lines(client, headers, po["id"])[0]
    create_grn(client, headers, po["id"], [receipt_line(line["id"], 10)], post=True)

    body = client.get(f"/api/purchase-orders/{po['id']}", headers=headers).get_json()
    assert body["purchaseOrder"]["status"] == "fully_received"


def test_nothing_can_be_received_against_a_draft_order(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"], approve=False)
    line = po_lines(client, headers, po["id"])[0]

    response = client.post("/api/goods-receipts", json={
        "purchaseOrderId": po["id"],
        "lines": [receipt_line(line["id"], 5)],
    }, headers=headers)
    assert response.status_code == 409
    assert response.get_json()["code"] == "PO_NOT_RECEIVABLE"


def test_nothing_can_be_received_against_a_cancelled_order(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]
    client.delete(f"/api/purchase-orders/{po['id']}", headers=headers)

    response = client.post("/api/goods-receipts", json={
        "purchaseOrderId": po["id"],
        "lines": [receipt_line(line["id"], 5)],
    }, headers=headers)
    assert response.status_code == 409


# ─── Cancelling gives the quantities back ────────────────────────────────────
def test_cancelling_a_posted_receipt_returns_the_quantities(
    app, client, owner, supplier
):
    """The reason the order columns are recomputed rather than incremented."""
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]
    grn = create_grn(client, headers, po["id"], [receipt_line(line["id"], 10)],
                     post=True)
    assert po_lines(client, headers, po["id"])[0]["quantityAccepted"] == "10.00"

    cancelled = client.post(f"/api/goods-receipts/{grn['id']}/cancel",
                            json={"reason": "Keyed against the wrong order."},
                            headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.get_json()["goodsReceipt"]["status"] == "cancelled"

    after = po_lines(client, headers, po["id"])[0]
    assert after["quantityReceived"] == "0.00"
    assert after["quantityAccepted"] == "0.00"


def test_cancelling_the_only_receipt_walks_the_order_status_back(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]
    grn = create_grn(client, headers, po["id"], [receipt_line(line["id"], 10)],
                     post=True)
    body = client.get(f"/api/purchase-orders/{po['id']}", headers=headers).get_json()
    assert body["purchaseOrder"]["status"] == "fully_received"

    client.post(f"/api/goods-receipts/{grn['id']}/cancel", headers=headers)
    body = client.get(f"/api/purchase-orders/{po['id']}", headers=headers).get_json()
    assert body["purchaseOrder"]["status"] == "sent"


def test_two_receipts_accumulate_and_one_cancellation_leaves_the_other(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]
    first = create_grn(client, headers, po["id"], [receipt_line(line["id"], 4)],
                       post=True)
    create_grn(client, headers, po["id"], [receipt_line(line["id"], 6)], post=True)
    assert po_lines(client, headers, po["id"])[0]["quantityAccepted"] == "10.00"

    client.post(f"/api/goods-receipts/{first['id']}/cancel", headers=headers)
    assert po_lines(client, headers, po["id"])[0]["quantityAccepted"] == "6.00"


def test_a_receipt_is_cancelled_never_deleted(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]
    grn = create_grn(client, headers, po["id"], [receipt_line(line["id"], 5)],
                     post=True)
    client.post(f"/api/goods-receipts/{grn['id']}/cancel",
                json={"reason": "Wrong order."}, headers=headers)

    body = client.get(f"/api/goods-receipts/{grn['id']}",
                      headers=headers).get_json()["goodsReceipt"]
    assert body["status"] == "cancelled"
    assert body["cancellationReason"] == "Wrong order."
    assert body["lines"][0]["quantityReceived"] == "5.00"


# ─── Outstanding ─────────────────────────────────────────────────────────────
def test_outstanding_is_measured_against_accepted_not_received(
    app, client, owner, supplier
):
    """Damaged goods stay outstanding: the supplier owes replacements."""
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]
    create_grn(client, headers, po["id"],
               [receipt_line(line["id"], 10, damaged=3)], post=True)

    body = client.get(
        f"/api/goods-receipts/purchase-orders/{po['id']}/outstanding",
        headers=headers,
    ).get_json()
    assert body["lines"][0]["quantityOrdered"] == "10.00"
    assert body["lines"][0]["quantityAccepted"] == "7.00"
    assert body["lines"][0]["quantityOutstanding"] == "3.00"


def test_outstanding_never_goes_negative_on_an_over_delivery(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]
    create_grn(client, headers, po["id"], [receipt_line(line["id"], 14)], post=True)

    body = client.get(
        f"/api/goods-receipts/purchase-orders/{po['id']}/outstanding",
        headers=headers,
    ).get_json()
    assert body["lines"][0]["quantityOutstanding"] == "0.00"


# ─── Three-way matching ──────────────────────────────────────────────────────
def test_three_way_matching_is_silent_until_receipts_are_used(
    app, client, owner, supplier
):
    """The condition that stops this shipping as a disaster. An organization
    that does not record deliveries must not have every invoice blocked."""
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    eid = make_invoice(app, owner, invoice_doc(reference=po["poNumber"]),
                       supplier_id=supplier["id"])
    link(client, headers, eid, po["id"])

    comparison = comparison_for(client, headers, eid)
    assert "invoice_before_goods" not in codes(comparison)
    assert comparison["outcome"] == "matched"
    assert comparison["delivery"]["checked"] is False


def test_once_receipts_are_used_an_invoice_with_no_delivery_is_blocked(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    # A receipt on some other order is what turns the control on.
    used = create_po(client, headers, supplier["id"])
    used_line = po_lines(client, headers, used["id"])[0]
    create_grn(client, headers, used["id"], [receipt_line(used_line["id"], 10)],
               post=True)

    po = create_po(client, headers, supplier["id"])
    eid = make_invoice(app, owner, invoice_doc(reference=po["poNumber"]),
                       supplier_id=supplier["id"])
    link(client, headers, eid, po["id"])

    comparison = comparison_for(client, headers, eid)
    finding = by_code(comparison, "invoice_before_goods")
    assert finding["severity"] == "blocking"
    assert comparison["outcome"] == "failed"
    assert comparison["blocked"] is True
    assert comparison["delivery"]["checked"] is True


def test_an_invoice_matching_what_was_accepted_passes(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]
    create_grn(client, headers, po["id"], [receipt_line(line["id"], 10)], post=True)

    eid = make_invoice(app, owner, invoice_doc(reference=po["poNumber"]),
                       supplier_id=supplier["id"])
    link(client, headers, eid, po["id"])

    comparison = comparison_for(client, headers, eid)
    assert comparison["counts"]["blocking"] == 0
    assert comparison["outcome"] == "matched"
    assert comparison["delivery"]["receiptCount"] == 1


def test_invoicing_more_than_was_accepted_is_blocked(app, client, owner, supplier):
    """Over-invoicing against delivery: the lorry came, it was short."""
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]
    create_grn(client, headers, po["id"], [receipt_line(line["id"], 6)], post=True)

    eid = make_invoice(app, owner, invoice_doc(reference=po["poNumber"]),
                       supplier_id=supplier["id"])
    link(client, headers, eid, po["id"])

    comparison = comparison_for(client, headers, eid)
    finding = by_code(comparison, "line_over_receipt")
    assert finding["severity"] == "blocking"
    assert "10" in finding["message"] and "6" in finding["message"]
    assert "4" in finding["message"]        # the shortfall, named


def test_invoicing_for_damaged_goods_is_blocked(app, client, owner, supplier):
    """Ten arrived, two smashed. An invoice for ten bills for the two broken
    ones, and "it turned up" is not the same as "we owe for it"."""
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]
    create_grn(client, headers, po["id"],
               [receipt_line(line["id"], 10, damaged=2)], post=True)

    eid = make_invoice(app, owner, invoice_doc(reference=po["poNumber"]),
                       supplier_id=supplier["id"])
    link(client, headers, eid, po["id"])

    comparison = comparison_for(client, headers, eid)
    finding = by_code(comparison, "line_over_receipt")
    assert finding["severity"] == "blocking"
    # The message distinguishes arrived from accepted, which is the whole point.
    assert "arrived" in finding["message"]
    assert "accepted" in finding["message"]


def test_invoicing_for_rejected_goods_is_blocked(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]
    create_grn(client, headers, po["id"],
               [receipt_line(line["id"], 10, rejected=3,
                             notes="Wrong specification, returned.")], post=True)

    eid = make_invoice(app, owner, invoice_doc(reference=po["poNumber"]),
                       supplier_id=supplier["id"])
    link(client, headers, eid, po["id"])

    assert "line_over_receipt" in codes(comparison_for(client, headers, eid))


def test_invoicing_a_line_with_no_delivery_at_all_is_blocked(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"], lines=[
        PO_LINE,
        {"description": "Stainless bolts", "sku": "BLT-1", "quantity": "5",
         "unitPrice": "200.00", "taxRate": "0"},
    ])
    lines = po_lines(client, headers, po["id"])
    # Only the hose arrived.
    create_grn(client, headers, po["id"], [receipt_line(lines[0]["id"], 10)],
               post=True)

    eid = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="2000.00", lines=[
            dict(INVOICE_LINE),
            {"description": "Stainless bolts", "product_name": "BLT-1",
             "quantity": 5, "unit_price": 200, "discount": None, "tax_rate": 0,
             "amount": 1000},
        ]),
        supplier_id=supplier["id"],
    )
    link(client, headers, eid, po["id"])

    comparison = comparison_for(client, headers, eid)
    finding = by_code(comparison, "line_not_received")
    assert finding["severity"] == "blocking"
    assert finding["lineNo"] == 2


def test_invoicing_less_than_arrived_is_fine(app, client, owner, supplier):
    """Billing in instalments behind the deliveries is normal."""
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]
    create_grn(client, headers, po["id"], [receipt_line(line["id"], 10)], post=True)

    eid = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="400.00",
                    lines=[{**INVOICE_LINE, "quantity": 4, "amount": 400}]),
        supplier_id=supplier["id"],
    )
    link(client, headers, eid, po["id"])

    comparison = comparison_for(client, headers, eid)
    assert comparison["counts"]["blocking"] == 0


def test_a_later_delivery_clears_the_block(app, client, owner, supplier):
    """The findings are recomputed, so recording the goods unblocks the
    invoice without anybody touching the invoice."""
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]
    create_grn(client, headers, po["id"], [receipt_line(line["id"], 6)], post=True)

    eid = make_invoice(app, owner, invoice_doc(reference=po["poNumber"]),
                       supplier_id=supplier["id"])
    link(client, headers, eid, po["id"])
    assert comparison_for(client, headers, eid)["blocked"] is True

    create_grn(client, headers, po["id"], [receipt_line(line["id"], 4)], post=True)
    after = comparison_for(client, headers, eid)
    assert "line_over_receipt" not in codes(after)
    assert after["blocked"] is False


def test_cancelling_the_delivery_blocks_the_invoice_again(
    app, client, owner, supplier
):
    """The assertion that the goods arrived has been withdrawn."""
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]
    grn = create_grn(client, headers, po["id"], [receipt_line(line["id"], 10)],
                     post=True)

    eid = make_invoice(app, owner, invoice_doc(reference=po["poNumber"]),
                       supplier_id=supplier["id"])
    link(client, headers, eid, po["id"])
    assert comparison_for(client, headers, eid)["blocked"] is False

    client.post(f"/api/goods-receipts/{grn['id']}/cancel", headers=headers)
    after = comparison_for(client, headers, eid)
    assert "invoice_before_goods" in codes(after)
    assert after["blocked"] is True


def test_a_draft_receipt_does_not_satisfy_an_invoice(app, client, owner, supplier):
    """The expensive version of the draft rule: a delivery note typed but not
    posted must not make an invoice payable."""
    headers = auth_header(app, owner)
    # Turn the control on with a receipt elsewhere.
    other = create_po(client, headers, supplier["id"])
    other_line = po_lines(client, headers, other["id"])[0]
    create_grn(client, headers, other["id"], [receipt_line(other_line["id"], 10)],
               post=True)

    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]
    create_grn(client, headers, po["id"], [receipt_line(line["id"], 10)])  # draft

    eid = make_invoice(app, owner, invoice_doc(reference=po["poNumber"]),
                       supplier_id=supplier["id"])
    link(client, headers, eid, po["id"])

    comparison = comparison_for(client, headers, eid)
    assert "invoice_before_goods" in codes(comparison)
    assert comparison["blocked"] is True


def test_the_three_way_block_can_be_turned_off(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]
    create_grn(client, headers, po["id"], [receipt_line(line["id"], 6)], post=True)

    eid = make_invoice(app, owner, invoice_doc(reference=po["poNumber"]),
                       supplier_id=supplier["id"])
    link(client, headers, eid, po["id"])
    assert comparison_for(client, headers, eid)["blocked"] is True

    client.put("/api/matching/settings", json={"requireGoodsReceipt": False},
               headers=headers)
    after = comparison_for(client, headers, eid)
    assert "line_over_receipt" not in codes(after)
    assert after["delivery"]["checked"] is False


def test_the_delivery_position_reaches_the_client_per_line(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]
    create_grn(client, headers, po["id"],
               [receipt_line(line["id"], 10, damaged=2)], post=True)

    eid = make_invoice(app, owner, invoice_doc(reference=po["poNumber"]),
                       supplier_id=supplier["id"])
    link(client, headers, eid, po["id"])

    comparison = comparison_for(client, headers, eid)
    po_line = comparison["lines"][0]["poLine"]
    assert po_line["quantityReceived"] == "10.00"
    assert po_line["quantityAccepted"] == "8.00"
    # Exact decimal strings, never JSON numbers.
    assert isinstance(po_line["quantityAccepted"], str)


def test_a_blocked_delivery_discrepancy_can_be_accepted_on_the_record(
    app, client, owner, supplier
):
    """Three-way findings go through the same override as every other
    blocking finding — nothing here is a dead end."""
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]
    create_grn(client, headers, po["id"], [receipt_line(line["id"], 6)], post=True)

    eid = make_invoice(app, owner, invoice_doc(reference=po["poNumber"]),
                       supplier_id=supplier["id"])
    link(client, headers, eid, po["id"])

    accepted = client.post(
        f"/api/matching/invoices/{eid}/override",
        json={"note": "Balance delivered direct to site; GRN to follow."},
        headers=headers,
    )
    assert accepted.status_code == 200
    body = accepted.get_json()
    assert body["comparison"]["blocked"] is False
    # Still reported, just no longer blocking.
    assert "line_over_receipt" in codes(body["comparison"])


# ─── Permissions and tenancy ─────────────────────────────────────────────────
def test_recording_a_delivery_needs_the_warehouse_permission(
    app, client, owner, supplier
):
    """An accountant can read receipts but must not be able to assert that
    goods they are about to pay for arrived."""
    org = make_org(app, owner, name="Acme", plan="pro")
    clerk = make_user(app, email="clerk@example.com", plan="pro")
    join_org(app, org, clerk, ACCOUNTANT)
    owner_headers = {**auth_header(app, owner), **org_header(app, owner, org)}

    from extensions import db
    from models import Supplier
    from suppliers import match_key_for

    with app.app_context():
        row = Supplier(organization_id=org["id"], name="Shared Vendor",
                       match_key=match_key_for("Shared Vendor"), currency="NGN")
        db.session.add(row)
        db.session.commit()
        supplier_id = row.id

    po = create_po(client, owner_headers, supplier_id)
    line = po_lines(client, owner_headers, po["id"])[0]

    clerk_headers = {**auth_header(app, clerk), **org_header(app, clerk, org)}
    assert client.get("/api/goods-receipts",
                      headers=clerk_headers).status_code == 200
    refused = client.post("/api/goods-receipts", json={
        "purchaseOrderId": po["id"],
        "lines": [receipt_line(line["id"], 5)],
    }, headers=clerk_headers)
    assert refused.status_code == 403


@pytest.mark.parametrize("role", [PROCUREMENT, ADMIN])
def test_procurement_and_admins_can_record_deliveries(
    app, client, owner, role
):
    org = make_org(app, owner, name=f"Org {role}", plan="pro")
    member = make_user(app, email=f"{role}@example.com", plan="pro")
    join_org(app, org, member, role)
    headers = {**auth_header(app, member), **org_header(app, member, org)}
    assert client.get("/api/goods-receipts", headers=headers).status_code == 200
    assert client.get("/api/goods-receipts/summary",
                      headers=headers).status_code == 200


def test_a_viewer_cannot_record_a_delivery(app, client, owner):
    org = make_org(app, owner, name="Watch Co", plan="pro")
    watcher = make_user(app, email="watcher@example.com", plan="pro")
    join_org(app, org, watcher, VIEWER)
    headers = {**auth_header(app, watcher), **org_header(app, watcher, org)}
    assert client.post("/api/goods-receipts", json={},
                       headers=headers).status_code == 403


def test_receipts_never_cross_an_organization_boundary(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]
    grn = create_grn(client, headers, po["id"], [receipt_line(line["id"], 5)])

    stranger = make_user(app, email="stranger@example.com", plan="pro")
    stranger_headers = auth_header(app, stranger)
    assert client.get(f"/api/goods-receipts/{grn['id']}",
                      headers=stranger_headers).status_code == 404
    assert client.get("/api/goods-receipts",
                      headers=stranger_headers).get_json()["total"] == 0


def test_goods_receipts_are_behind_the_payables_paywall(app, client):
    free = make_user(app, email="free@example.com", plan="free")
    response = client.get("/api/goods-receipts", headers=auth_header(app, free))
    assert response.status_code == 402
    assert response.get_json()["capability"] == "payables"


# ─── Numbering and listing ───────────────────────────────────────────────────
def test_receipts_are_numbered_per_organization(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]

    first = create_grn(client, headers, po["id"], [receipt_line(line["id"], 1)])
    second = create_grn(client, headers, po["id"], [receipt_line(line["id"], 1)])
    assert first["grnNumber"] == "GRN-0001"
    assert second["grnNumber"] == "GRN-0002"


def test_a_colliding_generated_number_is_retried(app, client, owner, supplier,
                                                 monkeypatch):
    import routes.goods_receipt_routes as module

    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]
    create_grn(client, headers, po["id"], [receipt_line(line["id"], 1)])

    calls = []
    real = module.next_grn_number

    def collide(organization_id):
        calls.append(organization_id)
        return "GRN-0001" if len(calls) == 1 else real(organization_id)

    monkeypatch.setattr(module, "next_grn_number", collide)
    response = client.post("/api/goods-receipts", json={
        "purchaseOrderId": po["id"],
        "lines": [receipt_line(line["id"], 2)],
    }, headers=headers)
    assert response.status_code == 201
    body = response.get_json()["goodsReceipt"]
    assert body["grnNumber"] == "GRN-0002"
    assert len(calls) == 2
    # The lines survived the rollback and retry.
    assert body["lines"][0]["quantityReceived"] == "2.00"


def test_a_duplicate_supplied_number_is_refused(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]
    create_grn(client, headers, po["id"], [receipt_line(line["id"], 1)],
               grnNumber="DN-5000")

    response = client.post("/api/goods-receipts", json={
        "purchaseOrderId": po["id"],
        "lines": [receipt_line(line["id"], 1)],
        "grnNumber": "DN-5000",
    }, headers=headers)
    assert response.status_code == 409


def test_the_list_filters_by_order_and_status(app, client, owner, supplier):
    headers = auth_header(app, owner)
    first = create_po(client, headers, supplier["id"])
    second = create_po(client, headers, supplier["id"])
    first_line = po_lines(client, headers, first["id"])[0]
    second_line = po_lines(client, headers, second["id"])[0]

    create_grn(client, headers, first["id"], [receipt_line(first_line["id"], 1)],
               post=True)
    create_grn(client, headers, second["id"], [receipt_line(second_line["id"], 1)])

    by_po = client.get(f"/api/goods-receipts?poId={first['id']}",
                       headers=headers).get_json()
    assert by_po["total"] == 1
    assert by_po["goodsReceipts"][0]["poNumber"] == first["poNumber"]

    drafts = client.get("/api/goods-receipts?status=draft",
                        headers=headers).get_json()
    assert drafts["total"] == 1


def test_the_summary_counts_by_status(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    line = po_lines(client, headers, po["id"])[0]
    create_grn(client, headers, po["id"], [receipt_line(line["id"], 1)], post=True)
    create_grn(client, headers, po["id"], [receipt_line(line["id"], 1)])

    body = client.get("/api/goods-receipts/summary", headers=headers).get_json()
    assert body["byStatus"]["posted"] == 1
    assert body["byStatus"]["draft"] == 1
    assert body["total"] == 2


# ─── Upload path ─────────────────────────────────────────────────────────────
def test_an_uploaded_invoice_is_checked_against_deliveries(
    app, client, owner, supplier, monkeypatch
):
    """The whole point, end to end: the document arrives, matches its order,
    and is still held because the goods did not."""
    import routes.extract_routes as er

    headers = auth_header(app, owner)
    other = create_po(client, headers, supplier["id"])
    other_line = po_lines(client, headers, other["id"])[0]
    create_grn(client, headers, other["id"], [receipt_line(other_line["id"], 10)],
               post=True)

    po = create_po(client, headers, supplier["id"])
    document = invoice_doc(reference=po["poNumber"])
    monkeypatch.setattr(er, "extract_document",
                        lambda pages, doc_type="invoice": document)
    response = client.post(
        "/api/extract",
        data={"file": (io.BytesIO(b"bytes"), "inv.pdf")},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["poMatch"]["blocked"] is True
    assert "invoice_before_goods" in [
        f["code"] for f in body["poMatch"]["findings"]
    ]
