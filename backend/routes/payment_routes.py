"""Payments to suppliers.

Not to be confused with `/api/billing/payments`, which is the opposite
direction: what a customer pays InvoiceParsed. These are payments a customer
makes to their own suppliers.

**Nothing here moves money.** Every endpoint records a payment somebody has
already made through their bank, or reads back what was recorded. There is no
code path that could initiate a transfer and no payment credential is held.
That is a deliberate product boundary, not an unfinished feature.

Recording a payment is gated on `payments:write`, which accountants hold and
viewers do not. Reading is `payments:read`.
"""
import logging

from flask import Blueprint, g, jsonify, request

from auth import api_or_login_required
from extensions import db
from models import Extraction, Supplier, SupplierPayment, User
from money import as_json
from payments import (
    OPEN_STATES,
    STATES,
    PaymentError,
    check_can_record,
    dispute,
    payables_summary,
    recompute_payment_state,
    refresh_overdue,
    settle_dispute,
    validate_payment,
    would_overpay,
)
from plans import PAYABLES, PAYABLES_FEATURE
from roles import PAYMENTS_READ, PAYMENTS_WRITE
from tenancy import (
    current_organization,
    require_capability,
    require_permission,
    scoped,
)

payment_bp = Blueprint("supplier_payments", __name__, url_prefix="/api/payments")
logger = logging.getLogger(__name__)

MAX_PAGE_SIZE = 100


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


def _invoice(eid):
    return (
        scoped(Extraction)
        .filter(
            Extraction.id == eid,
            Extraction.deleted_at.is_(None),
            Extraction.doc_type == "invoice",
        )
        .first()
    )


def _invoice_payload(record) -> dict:
    from payments import outstanding

    cache = {}
    rows = (
        scoped(SupplierPayment)
        .filter(SupplierPayment.extraction_id == record.id)
        .order_by(SupplierPayment.created_at.desc())
        .all()
    )
    return {
        "extractionId": record.id,
        "invoiceNumber": record.invoice_number,
        "supplierId": record.supplier_id,
        "vendorName": record.vendor_name,
        "currency": record.currency,
        "total": as_json(record.total),
        "amountPaid": as_json(record.amount_paid),
        "outstanding": as_json(outstanding(record)),
        "dueDate": record.due_date,
        "state": record.payment_state,
        "disputed": record.disputed_at is not None,
        "disputeReason": record.dispute_reason,
        "disputedBy": _user_label(record.disputed_by_user_id, cache),
        "payments": [
            row.public(
                recorded_by=_user_label(row.recorded_by_user_id, cache),
                voided_by=_user_label(row.voided_by_user_id, cache),
            )
            for row in rows
        ],
    }


# ─── The payables list ───────────────────────────────────────────────────────
@payment_bp.get("")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(PAYMENTS_READ)
def list_payables():
    """Invoices and where each one stands on payment.

    `refresh_overdue` runs here rather than from a scheduled job: overdue is
    the one state that changes without anybody touching anything, and this is
    the moment the answer matters.
    """
    organization = current_organization()
    if refresh_overdue(organization.id):
        db.session.commit()

    page = max(1, request.args.get("page", type=int) or 1)
    size = min(MAX_PAGE_SIZE, max(1, request.args.get("perPage", type=int) or 25))

    query = scoped(Extraction).filter(
        Extraction.deleted_at.is_(None),
        Extraction.doc_type == "invoice",
        Extraction.status == "completed",
    )

    state = (request.args.get("state") or "").strip().lower()
    if state == "open":
        query = query.filter(Extraction.payment_state.in_(OPEN_STATES))
    elif state in STATES:
        query = query.filter(Extraction.payment_state == state)

    supplier_id = (request.args.get("supplierId") or "").strip()
    if supplier_id:
        query = query.filter(Extraction.supplier_id == supplier_id)

    term = (request.args.get("q") or "").strip()
    if term:
        like = f"%{term}%"
        query = query.filter(
            db.or_(
                Extraction.invoice_number.ilike(like),
                Extraction.vendor_name.ilike(like),
            )
        )

    total = query.order_by(None).count()
    rows = (
        query.order_by(Extraction.due_date.asc().nullslast(),
                       Extraction.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    supplier_ids = {row.supplier_id for row in rows if row.supplier_id}
    names = {
        s.id: s.name
        for s in Supplier.query.filter(Supplier.id.in_(supplier_ids)).all()
    } if supplier_ids else {}

    from payments import outstanding

    items = [
        {
            "extractionId": row.id,
            "invoiceNumber": row.invoice_number,
            "vendorName": row.vendor_name,
            "supplierName": names.get(row.supplier_id),
            "supplierId": row.supplier_id,
            "invoiceDate": row.invoice_date,
            "dueDate": row.due_date,
            "currency": row.currency,
            "total": as_json(row.total),
            "amountPaid": as_json(row.amount_paid),
            "outstanding": as_json(outstanding(row)),
            "state": row.payment_state,
        }
        for row in rows
    ]

    return jsonify({
        "items": items,
        "page": page,
        "perPage": size,
        "total": total,
        "pages": max(1, (total + size - 1) // size),
    })


@payment_bp.get("/summary")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(PAYMENTS_READ)
def summary():
    """What is owed, by state and per currency."""
    organization = current_organization()
    if refresh_overdue(organization.id):
        db.session.commit()
    body = payables_summary(organization.id)
    body["outstandingByCurrency"] = [
        {"currency": row["currency"], "amount": as_json(row["amount"])}
        for row in body["outstandingByCurrency"]
    ]
    return jsonify(body)


# ─── One invoice ─────────────────────────────────────────────────────────────
@payment_bp.get("/invoices/<eid>")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(PAYMENTS_READ)
def get_invoice_payments(eid):
    record = _invoice(eid)
    if record is None:
        return jsonify({"error": "Invoice not found."}), 404
    recompute_payment_state(record)
    db.session.commit()
    return jsonify(_invoice_payload(record))


@payment_bp.post("/invoices/<eid>")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(PAYMENTS_WRITE)
def record_payment(eid):
    """Record a payment that has already been made.

    An overpayment is reported, not refused: paying twice by accident happens,
    and refusing to record money that has already left the bank account would
    make this ledger disagree with the bank — which is worse than a flagged
    overpayment.
    """
    record = _invoice(eid)
    if record is None:
        return jsonify({"error": "Invoice not found."}), 404

    try:
        check_can_record(record)
    except PaymentError as exc:
        return jsonify({"error": exc.message, "code": exc.code}), 409

    body = request.get_json(silent=True) or {}
    fields, errors = validate_payment(body, record)
    if errors:
        return jsonify({"error": "Some details need fixing.",
                        "fields": errors}), 400

    over = would_overpay(record, fields["amount"])

    payment = SupplierPayment(
        organization_id=record.organization_id,
        extraction_id=record.id,
        supplier_id=record.supplier_id,
        recorded_by_user_id=g.user.id,
        source=SupplierPayment.MANUAL,
        **fields,
    )
    db.session.add(payment)
    db.session.flush()
    recompute_payment_state(record)
    db.session.commit()

    payload = _invoice_payload(record)
    if over > 0:
        payload["warning"] = (
            f"This takes the total paid {as_json(over)} above the invoice. "
            "Recorded anyway — check for a duplicate payment."
        )
    return jsonify(payload), 201


@payment_bp.post("/<payment_id>/void")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(PAYMENTS_WRITE)
def void_payment(payment_id):
    """Void a payment recorded in error. Never deleted."""
    payment = scoped(SupplierPayment).filter(
        SupplierPayment.id == payment_id
    ).first()
    if payment is None:
        return jsonify({"error": "Payment not found."}), 404
    if payment.is_void:
        return jsonify({"error": "This payment is already void.",
                        "code": "ALREADY_VOID"}), 409

    body = request.get_json(silent=True) or {}
    reason = (body.get("reason") or "").strip()
    if not reason:
        return jsonify({
            "error": "Say why this payment is being voided.",
            "fields": {"reason": "Required."},
            "code": "REASON_REQUIRED",
        }), 400

    from datetime import datetime

    payment.voided_at = datetime.utcnow()
    payment.voided_by_user_id = g.user.id
    payment.void_reason = reason[:500]
    db.session.flush()

    record = _invoice(payment.extraction_id)
    if record is not None:
        recompute_payment_state(record)
    db.session.commit()
    return jsonify(_invoice_payload(record) if record else {"void": True})


# ─── Disputes ────────────────────────────────────────────────────────────────
@payment_bp.post("/invoices/<eid>/dispute")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(PAYMENTS_WRITE)
def raise_dispute(eid):
    """Mark an invoice disputed, so a payment run does not sweep it up."""
    record = _invoice(eid)
    if record is None:
        return jsonify({"error": "Invoice not found."}), 404

    body = request.get_json(silent=True) or {}
    try:
        dispute(record, user_id=g.user.id, reason=(body.get("reason") or ""))
    except PaymentError as exc:
        db.session.rollback()
        return jsonify({"error": exc.message, "code": exc.code}), 400
    db.session.commit()
    return jsonify(_invoice_payload(record))


@payment_bp.delete("/invoices/<eid>/dispute")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(PAYMENTS_WRITE)
def clear_dispute(eid):
    record = _invoice(eid)
    if record is None:
        return jsonify({"error": "Invoice not found."}), 404
    try:
        settle_dispute(record)
    except PaymentError as exc:
        db.session.rollback()
        return jsonify({"error": exc.message, "code": exc.code}), 409
    db.session.commit()
    return jsonify(_invoice_payload(record))
