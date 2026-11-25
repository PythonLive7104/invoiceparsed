"""Goods receipts.

What actually arrived. The leg of three-way matching that an order and an
invoice cannot supply between them, and the reason "we paid for goods we never
received" stops being possible.

Three things this layer refuses to do:

* **Count a draft.** Only a posted receipt moves an order's received totals or
  satisfies an invoice. A half-entered delivery note must not make anything
  payable.
* **Let a posted receipt be edited.** Invoices have been measured against it.
  To correct one, cancel it and record what actually arrived.
* **Delete anything.** A receipt is an assertion somebody made about a
  physical event. Cancelling is the strongest action available.

Recording a delivery is a warehouse job, not a finance one, so it is gated on
`goods_receipts:write` — held by administrators and procurement officers,
deliberately not by accountants, who should not be able to assert that goods
they are about to pay for turned up.
"""
import logging

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import IntegrityError

from auth import api_or_login_required
from extensions import db
from goods_receipts import (
    ReceiptError,
    can_receive,
    next_grn_number,
    outstanding_lines,
    recompute_received,
    replace_lines,
    transition,
    validate_lines,
)
from models import GoodsReceipt, PurchaseOrder, Supplier, User
from money import as_json
from plans import PAYABLES, PAYABLES_FEATURE
from roles import GOODS_RECEIPTS_READ, GOODS_RECEIPTS_WRITE
from tenancy import (
    current_organization,
    require_capability,
    require_permission,
    scoped,
)

goods_receipt_bp = Blueprint("goods_receipts", __name__,
                             url_prefix="/api/goods-receipts")
logger = logging.getLogger(__name__)

MAX_PAGE_SIZE = 100
NUMBER_RETRIES = 5
MAX_REASON = 500

EDITABLE = {
    "receivedDate": "received_date",
    "deliveryNoteRef": "delivery_note_ref",
    "carrier": "carrier",
    "notes": "notes",
}
MAX_LENGTHS = {
    "received_date": 40,
    "delivery_note_ref": 120,
    "carrier": 120,
}


# ─── Helpers ─────────────────────────────────────────────────────────────────
def _user_label(user_id, cache=None):
    if not user_id:
        return None
    if cache is not None and user_id in cache:
        return cache[user_id]
    user = User.query.filter_by(id=user_id).first()
    label = (user.name or user.email) if user else None
    if cache is not None:
        cache[user_id] = label
    return label


def _receipt(grn_id):
    return scoped(GoodsReceipt).filter(GoodsReceipt.id == grn_id).first()


def _detail(receipt):
    po = PurchaseOrder.query.filter_by(id=receipt.purchase_order_id).first()
    cache = {}
    payload = receipt.public(
        purchase_order=po,
        received_by=_user_label(receipt.received_by_user_id, cache),
        posted_by=_user_label(receipt.posted_by_user_id, cache),
    )
    if po is not None:
        supplier = Supplier.query.filter_by(id=po.supplier_id).first()
        payload["purchaseOrder"]["supplierName"] = supplier.name if supplier else None
    return {"goodsReceipt": payload}


def _apply_fields(receipt, body) -> dict:
    errors = {}
    for key, column in EDITABLE.items():
        if key not in body:
            continue
        value = body[key]
        value = None if value is None else str(value).strip() or None
        limit = MAX_LENGTHS.get(column)
        if value and limit and len(value) > limit:
            errors[key] = f"Keep this under {limit} characters."
            continue
        setattr(receipt, column, value)
    return errors


# ─── List and summary ────────────────────────────────────────────────────────
@goods_receipt_bp.get("")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(GOODS_RECEIPTS_READ)
def list_receipts():
    organization = current_organization()
    page = max(1, request.args.get("page", type=int) or 1)
    size = min(MAX_PAGE_SIZE, max(1, request.args.get("perPage", type=int) or 25))

    query = scoped(GoodsReceipt)

    status = (request.args.get("status") or "").strip().lower()
    if status in GoodsReceipt.STATUSES:
        query = query.filter(GoodsReceipt.status == status)

    po_id = (request.args.get("poId") or "").strip()
    if po_id:
        query = query.filter(GoodsReceipt.purchase_order_id == po_id)

    term = (request.args.get("q") or "").strip()
    if term:
        like = f"%{term}%"
        query = query.filter(
            db.or_(
                GoodsReceipt.grn_number.ilike(like),
                GoodsReceipt.delivery_note_ref.ilike(like),
            )
        )

    total = query.order_by(None).count()
    rows = (
        query.order_by(GoodsReceipt.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    # The orders for this page in one query rather than one per row.
    po_ids = {row.purchase_order_id for row in rows}
    orders = {
        po.id: po
        for po in PurchaseOrder.query.filter(PurchaseOrder.id.in_(po_ids)).all()
    } if po_ids else {}

    items = []
    for row in rows:
        po = orders.get(row.purchase_order_id)
        item = row.list_item()
        item["poNumber"] = po.po_number if po else None
        item["poStatus"] = po.status if po else None
        items.append(item)

    pages = max(1, (total + size - 1) // size)
    return jsonify({
        "goodsReceipts": items,
        "page": page,
        "perPage": size,
        "total": total,
        "pages": pages,
        "organizationId": organization.id,
    })


@goods_receipt_bp.get("/summary")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(GOODS_RECEIPTS_READ)
def summary():
    """Counts for the receipts page, leading with what is unfinished.

    A draft receipt is the one that costs money: it looks recorded to the
    person who typed it and counts for nothing until posted, so an invoice
    against it blocks and nobody knows why.
    """
    organization = current_organization()
    rows = (
        db.session.query(GoodsReceipt.status, db.func.count(GoodsReceipt.id))
        .filter(GoodsReceipt.organization_id == organization.id)
        .group_by(GoodsReceipt.status)
        .all()
    )
    counts = {status: 0 for status in GoodsReceipt.STATUSES}
    for status, count in rows:
        if status in counts:
            counts[status] = count

    # Orders that are open and have had nothing delivered yet.
    awaiting = (
        db.session.query(db.func.count(PurchaseOrder.id))
        .filter(
            PurchaseOrder.organization_id == organization.id,
            PurchaseOrder.status.in_(sorted(PurchaseOrder.OPEN_STATUSES)),
        )
        .scalar()
    ) or 0

    return jsonify({
        "byStatus": counts,
        "total": sum(counts.values()),
        "openOrders": awaiting,
    })


# ─── What is outstanding on an order ─────────────────────────────────────────
@goods_receipt_bp.get("/purchase-orders/<po_id>/outstanding")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(GOODS_RECEIPTS_READ)
def outstanding(po_id):
    """What is still owed on each line, for pre-filling a new receipt.

    Measured against what was ACCEPTED, so goods that arrived damaged show as
    still outstanding — which is the truth: the supplier owes replacements or
    a credit.
    """
    po = scoped(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if po is None:
        return jsonify({"error": "Purchase order not found."}), 404

    supplier = Supplier.query.filter_by(id=po.supplier_id).first()
    lines = outstanding_lines(po)
    return jsonify({
        "purchaseOrderId": po.id,
        "poNumber": po.po_number,
        "status": po.status,
        "currency": po.currency,
        "supplierName": supplier.name if supplier else None,
        "receivable": po.status in {
            PurchaseOrder.APPROVED, PurchaseOrder.SENT,
            PurchaseOrder.PARTIALLY_RECEIVED, PurchaseOrder.FULLY_RECEIVED,
        },
        "lines": [
            {
                **line,
                "quantityOrdered": as_json(line["quantityOrdered"]),
                "quantityAccepted": as_json(line["quantityAccepted"]),
                "quantityOutstanding": as_json(line["quantityOutstanding"]),
            }
            for line in lines
        ],
    })


# ─── Create, read, edit ──────────────────────────────────────────────────────
@goods_receipt_bp.post("")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(GOODS_RECEIPTS_WRITE)
def create_receipt():
    """Record a delivery against a purchase order, as a draft."""
    organization = current_organization()
    body = request.get_json(silent=True) or {}

    po_id = (body.get("purchaseOrderId") or "").strip()
    if not po_id:
        return jsonify({"error": "Choose a purchase order.",
                        "fields": {"purchaseOrderId": "Required."}}), 400
    po = scoped(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if po is None:
        return jsonify({"error": "Purchase order not found."}), 404

    try:
        can_receive(po)
    except ReceiptError as exc:
        return jsonify({"error": exc.message, "code": exc.code}), 409

    clean, errors = validate_lines(body.get("lines"), po)
    field_errors = dict(errors)

    receipt = GoodsReceipt(
        organization_id=organization.id,
        purchase_order_id=po.id,
        status=GoodsReceipt.DRAFT,
        received_by_user_id=g.user.id,
        created_by_user_id=g.user.id,
    )
    field_errors.update(_apply_fields(receipt, body))
    if field_errors:
        return jsonify({"error": "Some details need fixing.",
                        "fields": field_errors}), 400

    replace_lines(receipt, clean)

    supplied = (body.get("grnNumber") or "").strip()
    for attempt in range(NUMBER_RETRIES):
        receipt.grn_number = supplied or next_grn_number(organization.id)
        db.session.add(receipt)
        try:
            db.session.commit()
            break
        except IntegrityError:
            db.session.rollback()
            if supplied:
                return jsonify({
                    "error": f"A receipt numbered {supplied} already exists.",
                    "fields": {"grnNumber": "Already used."},
                }), 409
            if attempt == NUMBER_RETRIES - 1:
                logger.warning("GRN numbering exhausted for org %s", organization.id)
                return jsonify({
                    "error": "Couldn't allocate a receipt number. Try again.",
                    "code": "NUMBERING_BUSY",
                }), 503
            # Deliberately NOT re-added here: the next pass through the loop
            # adds it, and adding it now would leave a pending row carrying the
            # colliding number for next_grn_number()'s query to autoflush.

    return jsonify(_detail(receipt)), 201


@goods_receipt_bp.get("/<grn_id>")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(GOODS_RECEIPTS_READ)
def get_receipt(grn_id):
    receipt = _receipt(grn_id)
    if receipt is None:
        return jsonify({"error": "Goods receipt not found."}), 404
    return jsonify(_detail(receipt))


@goods_receipt_bp.patch("/<grn_id>")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(GOODS_RECEIPTS_WRITE)
def update_receipt(grn_id):
    """Edit a draft receipt. A posted one is what invoices were measured
    against, so it cannot be changed — only cancelled and re-recorded."""
    receipt = _receipt(grn_id)
    if receipt is None:
        return jsonify({"error": "Goods receipt not found."}), 404
    if not receipt.is_editable:
        return jsonify({
            "error": (f"This receipt is {receipt.status} and can no longer be "
                      "edited. Cancel it and record a new one to correct what "
                      "arrived."),
            "code": "NOT_EDITABLE",
        }), 409

    po = PurchaseOrder.query.filter_by(id=receipt.purchase_order_id).first()
    if po is None:
        return jsonify({"error": "Purchase order not found."}), 404

    body = request.get_json(silent=True) or {}
    errors = _apply_fields(receipt, body)

    if "lines" in body:
        clean, line_errors = validate_lines(body.get("lines"), po)
        errors.update(line_errors)
        if not errors:
            replace_lines(receipt, clean)

    if errors:
        db.session.rollback()
        return jsonify({"error": "Some details need fixing.",
                        "fields": errors}), 400

    db.session.commit()
    return jsonify(_detail(receipt))


# ─── Lifecycle ───────────────────────────────────────────────────────────────
@goods_receipt_bp.post("/<grn_id>/post")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(GOODS_RECEIPTS_WRITE)
def post_receipt(grn_id):
    """Post a receipt: it now counts toward what has been received.

    This is the write that moves the order's totals and can unblock an
    invoice, which is why it is a deliberate step rather than a side effect of
    saving a form.
    """
    receipt = _receipt(grn_id)
    if receipt is None:
        return jsonify({"error": "Goods receipt not found."}), 404

    po = PurchaseOrder.query.filter_by(id=receipt.purchase_order_id).first()
    if po is None:
        return jsonify({"error": "Purchase order not found."}), 404

    try:
        can_receive(po)
        transition(receipt, GoodsReceipt.POSTED, user_id=g.user.id)
    except ReceiptError as exc:
        db.session.rollback()
        return jsonify({"error": exc.message, "code": exc.code}), 409

    db.session.flush()
    recompute_received(po)
    db.session.commit()
    return jsonify(_detail(receipt))


@goods_receipt_bp.post("/<grn_id>/cancel")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(GOODS_RECEIPTS_WRITE)
def cancel_receipt(grn_id):
    """Cancel a receipt. Posted or draft — nothing is ever deleted.

    Cancelling a posted receipt gives back the quantities it contributed, so
    an invoice that was satisfied by it may become blocked again. That is
    correct: the assertion that the goods arrived has been withdrawn.
    """
    receipt = _receipt(grn_id)
    if receipt is None:
        return jsonify({"error": "Goods receipt not found."}), 404

    body = request.get_json(silent=True) or {}
    reason = (body.get("reason") or "").strip()[:MAX_REASON] or None

    po = PurchaseOrder.query.filter_by(id=receipt.purchase_order_id).first()
    try:
        transition(receipt, GoodsReceipt.CANCELLED, user_id=g.user.id,
                   reason=reason)
    except ReceiptError as exc:
        db.session.rollback()
        return jsonify({"error": exc.message, "code": exc.code}), 409

    db.session.flush()
    if po is not None:
        recompute_received(po)
    db.session.commit()
    return jsonify(_detail(receipt))
