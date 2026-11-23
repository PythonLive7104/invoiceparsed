"""Invoice-to-purchase-order matching.

Three things to know before changing a permission in here.

**Tolerances are a control, not a preference.** Widening a tolerance is exactly
how you make the whole check stop working, so settings are gated on
`organization:settings` — the admin gate — and not on the permission held by
the people who process invoices all day.

**Linking is bookkeeping; overriding is authority.** Saying which order an
invoice belongs to is a fact about the invoice, so it needs `documents:write`:
an accountant doing accounts payable can do it, a viewer cannot. Accepting a
blocking discrepancy anyway is an authorization, so it needs `approvals:act`,
the same gate as approving an order, and the note explaining it is mandatory.

**The list reads the cached verdict; the detail recomputes it.** Findings are
always recomputed from the live document, and reading one refreshes the cached
columns the list filters on. The list therefore trails the truth by at most one
read of the invoice it concerns — which is acceptable for a filter, and is why
nothing in the system is allowed to act on the cached columns.
"""
import logging
from datetime import datetime

from flask import Blueprint, g, jsonify, request

from auth import api_or_login_required
from documents import load_document
from extensions import db
from models import Extraction, InvoiceMatch, PurchaseOrder, Supplier, User
from money import as_json, rate, to_decimal
from po_matching import (
    evaluate,
    find_candidates,
    recompute_invoiced,
    settings_for,
)
from roles import (
    APPROVALS_ACT,
    DOCUMENTS_WRITE,
    ORG_SETTINGS,
    PURCHASE_ORDERS_READ,
)
from tenancy import current_organization, require_permission, scoped

match_bp = Blueprint("matching", __name__, url_prefix="/api/matching")
logger = logging.getLogger(__name__)

MAX_PAGE_SIZE = 100
MAX_NOTE = 500

# Which tolerances a client may set, and how each is parsed. Percentages and
# quantities keep 4 places (`rate`); so do the monetary bounds, because they are
# compared against Numeric(18, 4) columns and silently rounding a bound to 2
# places would change the control an organization thought it had configured.
NUMERIC_SETTINGS = {
    "priceTolerancePercent": "price_tolerance_percent",
    "priceToleranceAmount": "price_tolerance_amount",
    "quantityTolerancePercent": "quantity_tolerance_percent",
    "quantityToleranceAmount": "quantity_tolerance_amount",
    "totalTolerancePercent": "total_tolerance_percent",
    "totalToleranceAmount": "total_tolerance_amount",
}
FLAG_SETTINGS = {
    "requirePoReference": "require_po_reference",
    "blockUnapprovedPo": "block_unapproved_po",
    "autoConfirmExact": "auto_confirm_exact",
}

# A tolerance above this is not a tolerance. Percentages are capped at 100
# because "within 150% of the agreed price" is not a check, and absolute bounds
# are capped simply to keep an accidental extra digit from disabling matching
# across the organization without anyone noticing.
MAX_PERCENT = to_decimal("100")
MAX_AMOUNT = to_decimal("1000000")


# ─── Helpers ─────────────────────────────────────────────────────────────────
def _invoice(eid):
    """A live, completed invoice in the acting organization, or None."""
    return (
        scoped(Extraction)
        .filter(
            Extraction.id == eid,
            Extraction.deleted_at.is_(None),
            Extraction.doc_type == "invoice",
        )
        .first()
    )


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


def _detail(record, match, document=None):
    """One invoice's match, with the comparison recomputed from live data."""
    document = document if document is not None else (load_document(record) or {})
    comparison = evaluate(record, document, match=match)
    db.session.commit()  # persist the refreshed cached verdict

    if match is None:
        return {
            "extractionId": record.id,
            "match": None,
            "comparison": comparison,
            "invoice": {
                "id": record.id,
                "fileName": record.file_name,
                "vendorName": record.vendor_name,
                "invoiceNumber": record.invoice_number,
                "invoiceDate": record.invoice_date,
                "currency": record.currency,
                "total": as_json(record.total),
                "supplierId": record.supplier_id,
                "poReference": document.get("purchase_order_reference"),
            },
        }

    po = PurchaseOrder.query.filter_by(
        id=match.purchase_order_id, organization_id=record.organization_id
    ).first()
    supplier = (
        Supplier.query.filter_by(id=po.supplier_id).first() if po is not None else None
    )
    cache = {}
    payload = match.public(
        purchase_order=po,
        extraction=record,
        comparison=comparison,
        confirmed_by=_user_label(match.confirmed_by_user_id, cache),
        overridden_by=_user_label(match.overridden_by_user_id, cache),
    )
    if po is not None:
        payload["purchaseOrder"]["supplierName"] = supplier.name if supplier else None
        payload["purchaseOrder"]["reference"] = po.reference
        payload["purchaseOrder"]["orderDate"] = po.order_date
    payload["invoice"]["poReference"] = document.get("purchase_order_reference")
    return {
        "extractionId": record.id,
        "match": payload,
        "comparison": comparison,
    }


# ─── Settings ────────────────────────────────────────────────────────────────
@match_bp.get("/settings")
@api_or_login_required
@require_permission(PURCHASE_ORDERS_READ)
def get_settings():
    organization = current_organization()
    settings = settings_for(organization.id)
    db.session.commit()  # the defaults row, if this was the first read
    return jsonify({
        "settings": settings.public(),
        "updatedBy": _user_label(settings.updated_by_user_id),
    })


@match_bp.put("/settings")
@api_or_login_required
@require_permission(ORG_SETTINGS)
def update_settings():
    """Change the tolerances.

    Admin-gated on purpose: see the module docstring. A tolerance nobody can
    see being widened is not a control.
    """
    organization = current_organization()
    settings = settings_for(organization.id)
    body = request.get_json(silent=True) or {}
    errors = {}

    for key, column in NUMERIC_SETTINGS.items():
        if key not in body:
            continue
        raw = body[key]
        parsed = rate(raw) if raw not in (None, "") else to_decimal("0")
        if parsed is None:
            errors[key] = "Enter a number."
            continue
        if parsed < 0:
            errors[key] = "A tolerance cannot be negative."
            continue
        ceiling = MAX_PERCENT if key.endswith("Percent") else MAX_AMOUNT
        if parsed > ceiling:
            errors[key] = (
                f"Must be {ceiling:,.0f} or less. A bound larger than this "
                "switches the check off rather than loosening it."
            )
            continue
        setattr(settings, column, parsed)

    for key, column in FLAG_SETTINGS.items():
        if key in body:
            setattr(settings, column, bool(body[key]))

    if errors:
        db.session.rollback()
        return jsonify({"error": "Some tolerances are not valid.",
                        "fields": errors}), 400

    settings.updated_by_user_id = g.user.id
    db.session.commit()
    return jsonify({"settings": settings.public(),
                    "updatedBy": _user_label(settings.updated_by_user_id)})


# ─── Exception list ──────────────────────────────────────────────────────────
@match_bp.get("/invoices")
@api_or_login_required
@require_permission(PURCHASE_ORDERS_READ)
def list_matches():
    """Invoices and where each one stands against its order.

    `state=unmatched` is a LEFT JOIN rather than a filter on the match table,
    because an invoice with no match row is the single most important thing
    this list has to be able to show: an invoice nobody has tied to an order is
    invisible to every query that starts from the match table.
    """
    organization = current_organization()
    page = max(1, request.args.get("page", type=int) or 1)
    size = min(MAX_PAGE_SIZE, max(1, request.args.get("pageSize", type=int) or 25))

    query = (
        db.session.query(Extraction, InvoiceMatch)
        .outerjoin(
            InvoiceMatch,
            db.and_(
                InvoiceMatch.extraction_id == Extraction.id,
                # Redundant today: a match's organization is always copied from
                # the extraction it is created for, so the join alone is
                # tenant-safe. Stated anyway, because that is an invariant of
                # the WRITE path, and a tenancy hole opened by a future change
                # to that path should fail a query rather than leak a row.
                InvoiceMatch.organization_id == Extraction.organization_id,
            ),
        )
        .filter(
            Extraction.organization_id == organization.id,
            Extraction.deleted_at.is_(None),
            Extraction.doc_type == "invoice",
            Extraction.status == "completed",
        )
    )

    state = (request.args.get("state") or "").strip().lower()
    if state == "unmatched":
        query = query.filter(InvoiceMatch.id.is_(None))
    elif state == "matched":
        query = query.filter(InvoiceMatch.outcome == InvoiceMatch.MATCHED)
    elif state == "exceptions":
        # Everything a person still has to deal with: an unmatched invoice, or
        # a match whose figures did not agree and which nobody has accepted.
        query = query.filter(
            db.or_(
                InvoiceMatch.id.is_(None),
                db.and_(
                    InvoiceMatch.outcome != InvoiceMatch.MATCHED,
                    InvoiceMatch.overridden_at.is_(None),
                ),
            )
        )
    elif state == "blocked":
        query = query.filter(
            InvoiceMatch.blocking_count > 0,
            InvoiceMatch.overridden_at.is_(None),
        )
    elif state == "overridden":
        query = query.filter(InvoiceMatch.overridden_at.isnot(None))

    outcome = (request.args.get("outcome") or "").strip().lower()
    if outcome in InvoiceMatch.OUTCOMES:
        query = query.filter(InvoiceMatch.outcome == outcome)

    status = (request.args.get("status") or "").strip().lower()
    if status in InvoiceMatch.STATUSES:
        query = query.filter(InvoiceMatch.status == status)

    po_id = (request.args.get("poId") or "").strip()
    if po_id:
        query = query.filter(InvoiceMatch.purchase_order_id == po_id)

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
                Extraction.file_name.ilike(like),
            )
        )

    total = query.count()
    rows = (
        query.order_by(Extraction.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    # The orders and suppliers for this page in one query each, rather than one
    # per row.
    po_ids = {match.purchase_order_id for _record, match in rows if match}
    orders = {
        po.id: po
        for po in PurchaseOrder.query.filter(PurchaseOrder.id.in_(po_ids)).all()
    } if po_ids else {}
    supplier_ids = {
        record.supplier_id for record, _match in rows if record.supplier_id
    }
    suppliers = {
        supplier.id: supplier.name
        for supplier in Supplier.query.filter(Supplier.id.in_(supplier_ids)).all()
    } if supplier_ids else {}

    items = []
    for record, match in rows:
        po = orders.get(match.purchase_order_id) if match else None
        items.append({
            "extractionId": record.id,
            "fileName": record.file_name,
            "vendorName": record.vendor_name,
            "supplierName": suppliers.get(record.supplier_id),
            "invoiceNumber": record.invoice_number,
            "invoiceDate": record.invoice_date,
            "currency": record.currency,
            "total": as_json(record.total),
            "createdAt": record.created_at.isoformat() + "Z"
            if record.created_at else None,
            "match": None if match is None else {
                "id": match.id,
                "status": match.status,
                "method": match.method,
                "outcome": match.outcome,
                "blockingCount": match.blocking_count or 0,
                "reviewCount": match.review_count or 0,
                "overridden": match.is_overridden,
                "purchaseOrderId": match.purchase_order_id,
                "poNumber": po.po_number if po else None,
                "poStatus": po.status if po else None,
                "poTotal": as_json(po.total) if po else None,
            },
        })

    return jsonify({
        "items": items,
        "page": page,
        "pageSize": size,
        "total": total,
        "hasMore": page * size < total,
    })


@match_bp.get("/summary")
@api_or_login_required
@require_permission(PURCHASE_ORDERS_READ)
def summary():
    """Counts for the exception dashboard.

    Leads with what somebody has to act on. "47 invoices matched" is reassuring
    and useless; "3 blocked, 6 unmatched" is the work.
    """
    organization = current_organization()
    base = (
        db.session.query(Extraction.id)
        .filter(
            Extraction.organization_id == organization.id,
            Extraction.deleted_at.is_(None),
            Extraction.doc_type == "invoice",
            Extraction.status == "completed",
        )
    )
    invoice_total = base.count()

    rows = (
        db.session.query(InvoiceMatch.outcome, db.func.count(InvoiceMatch.id))
        .join(Extraction, Extraction.id == InvoiceMatch.extraction_id)
        .filter(
            InvoiceMatch.organization_id == organization.id,
            Extraction.deleted_at.is_(None),
        )
        .group_by(InvoiceMatch.outcome)
        .all()
    )
    by_outcome = {outcome: 0 for outcome in InvoiceMatch.OUTCOMES}
    matched_total = 0
    for outcome, count in rows:
        matched_total += count
        if outcome in by_outcome:
            by_outcome[outcome] = count

    blocked = (
        db.session.query(db.func.count(InvoiceMatch.id))
        .join(Extraction, Extraction.id == InvoiceMatch.extraction_id)
        .filter(
            InvoiceMatch.organization_id == organization.id,
            Extraction.deleted_at.is_(None),
            InvoiceMatch.blocking_count > 0,
            InvoiceMatch.overridden_at.is_(None),
        )
        .scalar()
    ) or 0

    awaiting = (
        db.session.query(db.func.count(InvoiceMatch.id))
        .join(Extraction, Extraction.id == InvoiceMatch.extraction_id)
        .filter(
            InvoiceMatch.organization_id == organization.id,
            Extraction.deleted_at.is_(None),
            InvoiceMatch.status == InvoiceMatch.SUGGESTED,
        )
        .scalar()
    ) or 0

    overridden = (
        db.session.query(db.func.count(InvoiceMatch.id))
        .join(Extraction, Extraction.id == InvoiceMatch.extraction_id)
        .filter(
            InvoiceMatch.organization_id == organization.id,
            Extraction.deleted_at.is_(None),
            InvoiceMatch.overridden_at.isnot(None),
        )
        .scalar()
    ) or 0

    return jsonify({
        "invoices": invoice_total,
        "unmatched": max(0, invoice_total - matched_total),
        "byOutcome": by_outcome,
        "blocked": blocked,
        "awaitingConfirmation": awaiting,
        "overridden": overridden,
    })


# ─── One invoice ─────────────────────────────────────────────────────────────
@match_bp.get("/invoices/<eid>")
@api_or_login_required
@require_permission(PURCHASE_ORDERS_READ)
def get_match(eid):
    record = _invoice(eid)
    if record is None:
        return jsonify({"error": "Invoice not found."}), 404
    match = scoped(InvoiceMatch).filter(InvoiceMatch.extraction_id == eid).first()
    return jsonify(_detail(record, match))


@match_bp.get("/invoices/<eid>/candidates")
@api_or_login_required
@require_permission(PURCHASE_ORDERS_READ)
def candidates(eid):
    """Orders this invoice might belong to, for someone choosing by hand."""
    record = _invoice(eid)
    if record is None:
        return jsonify({"error": "Invoice not found."}), 404
    document = load_document(record) or {}
    found = find_candidates(
        record.organization_id, document, supplier_id=record.supplier_id
    )
    db.session.commit()  # the settings row, if this was the first read

    supplier_ids = {
        entry["purchaseOrder"].supplier_id for entry in found
        if entry["purchaseOrder"].supplier_id
    }
    names = {
        supplier.id: supplier.name
        for supplier in Supplier.query.filter(Supplier.id.in_(supplier_ids)).all()
    } if supplier_ids else {}

    return jsonify({
        "reference": document.get("purchase_order_reference"),
        "candidates": [
            {
                "purchaseOrderId": entry["purchaseOrder"].id,
                "poNumber": entry["purchaseOrder"].po_number,
                "status": entry["purchaseOrder"].status,
                "currency": entry["purchaseOrder"].currency,
                "total": as_json(entry["purchaseOrder"].total),
                "orderDate": entry["purchaseOrder"].order_date,
                "reference": entry["purchaseOrder"].reference,
                "supplierId": entry["purchaseOrder"].supplier_id,
                "supplierName": names.get(entry["purchaseOrder"].supplier_id),
                "method": entry["method"],
                "score": entry["score"],
            }
            for entry in found
        ],
    })


@match_bp.post("/invoices/<eid>/link")
@api_or_login_required
@require_permission(DOCUMENTS_WRITE)
def link(eid):
    """Attach this invoice to an order, replacing any existing link.

    Confirmed outright: a person naming the order is the strongest signal there
    is, and leaving their own choice sitting as a "suggestion" would be absurd.
    Confirming does not approve anything — a blocking finding still blocks.
    """
    record = _invoice(eid)
    if record is None:
        return jsonify({"error": "Invoice not found."}), 404

    body = request.get_json(silent=True) or {}
    po_id = (body.get("purchaseOrderId") or "").strip()
    if not po_id:
        return jsonify({"error": "Choose a purchase order.",
                        "fields": {"purchaseOrderId": "Required."}}), 400

    po = scoped(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if po is None:
        return jsonify({"error": "Purchase order not found."}), 404

    match = scoped(InvoiceMatch).filter(InvoiceMatch.extraction_id == eid).first()
    previous_po_id = match.purchase_order_id if match else None
    if match is None:
        match = InvoiceMatch(
            organization_id=record.organization_id,
            extraction_id=record.id,
            purchase_order_id=po.id,
            created_by_user_id=g.user.id,
        )
        db.session.add(match)

    match.purchase_order_id = po.id
    match.method = InvoiceMatch.BY_MANUAL
    match.score = 1.0
    match.status = InvoiceMatch.CONFIRMED
    match.confirmed_by_user_id = g.user.id
    match.confirmed_at = datetime.utcnow()
    # A link moved to a different order clears the override: the discrepancies
    # somebody accepted were about the old order, and carrying their acceptance
    # across to a different one would launder it.
    if previous_po_id and previous_po_id != po.id:
        match.override_note = None
        match.overridden_by_user_id = None
        match.overridden_at = None

    db.session.flush()
    recompute_invoiced(po)
    if previous_po_id and previous_po_id != po.id:
        previous = PurchaseOrder.query.filter_by(id=previous_po_id).first()
        if previous is not None:
            recompute_invoiced(previous)
    db.session.commit()
    return jsonify(_detail(record, match))


@match_bp.post("/invoices/<eid>/reject")
@api_or_login_required
@require_permission(DOCUMENTS_WRITE)
def reject(eid):
    """Say that the suggested order is not the right one.

    Kept as a rejected row rather than deleted, so the same suggestion is not
    offered again on the next upload or recompute, and so the fact that
    somebody looked is on the record.
    """
    record = _invoice(eid)
    if record is None:
        return jsonify({"error": "Invoice not found."}), 404
    match = scoped(InvoiceMatch).filter(InvoiceMatch.extraction_id == eid).first()
    if match is None:
        return jsonify({"error": "This invoice is not linked to an order.",
                        "code": "NOT_LINKED"}), 404

    po_id = match.purchase_order_id
    match.status = InvoiceMatch.REJECTED
    match.confirmed_by_user_id = None
    match.confirmed_at = None
    match.override_note = None
    match.overridden_by_user_id = None
    match.overridden_at = None
    db.session.flush()
    po = PurchaseOrder.query.filter_by(id=po_id).first()
    if po is not None:
        recompute_invoiced(po)
    db.session.commit()
    return jsonify(_detail(record, match))


@match_bp.delete("/invoices/<eid>")
@api_or_login_required
@require_permission(DOCUMENTS_WRITE)
def unlink(eid):
    """Remove the link entirely, so matching can suggest again from scratch."""
    record = _invoice(eid)
    if record is None:
        return jsonify({"error": "Invoice not found."}), 404
    match = scoped(InvoiceMatch).filter(InvoiceMatch.extraction_id == eid).first()
    if match is None:
        return jsonify({"error": "This invoice is not linked to an order.",
                        "code": "NOT_LINKED"}), 404

    po_id = match.purchase_order_id
    db.session.delete(match)
    db.session.flush()
    po = PurchaseOrder.query.filter_by(id=po_id).first()
    if po is not None:
        recompute_invoiced(po)
    db.session.commit()
    return jsonify(_detail(record, None))


@match_bp.post("/invoices/<eid>/override")
@api_or_login_required
@require_permission(APPROVALS_ACT)
def override(eid):
    """Accept this invoice's discrepancies, with a reason, on the record.

    Gated on `approvals:act`, not on the permission used to process invoices:
    the whole point of a blocking finding is that clearing it is a decision
    somebody with authority makes and signs.

    Deliberately no self-override rule, unlike approving a purchase order. The
    conflict a PO's self-approval rule guards against is a person authorizing
    their own commitment; whoever uploaded a supplier's invoice has no such
    stake in it, and refusing here would only mean the person who scanned the
    document cannot be the one who resolves it.
    """
    record = _invoice(eid)
    if record is None:
        return jsonify({"error": "Invoice not found."}), 404
    match = scoped(InvoiceMatch).filter(InvoiceMatch.extraction_id == eid).first()
    if match is None or match.status == InvoiceMatch.REJECTED:
        return jsonify({
            "error": "Link this invoice to a purchase order before accepting "
                     "its discrepancies.",
            "code": "NOT_LINKED",
        }), 409

    body = request.get_json(silent=True) or {}
    note = (body.get("note") or "").strip()
    if not note:
        return jsonify({
            "error": "Explain why these discrepancies are acceptable.",
            "fields": {"note": "Required."},
            "code": "NOTE_REQUIRED",
        }), 400

    document = load_document(record) or {}
    comparison = evaluate(record, document, match=match)
    if comparison["counts"].get("blocking", 0) == 0 and \
            comparison["counts"].get("review", 0) == 0:
        db.session.commit()
        return jsonify({
            "error": "There is nothing to accept: this invoice matches its "
                     "order.",
            "code": "NOTHING_TO_OVERRIDE",
        }), 409

    match.override_note = note[:MAX_NOTE]
    match.overridden_by_user_id = g.user.id
    match.overridden_at = datetime.utcnow()
    if match.status == InvoiceMatch.SUGGESTED:
        # Accepting the figures means accepting the link they were measured
        # against; leaving it unconfirmed would keep the invoice out of the
        # order's invoiced total it was just checked against.
        match.status = InvoiceMatch.CONFIRMED
        match.confirmed_by_user_id = g.user.id
        match.confirmed_at = datetime.utcnow()
    db.session.flush()
    po = PurchaseOrder.query.filter_by(id=match.purchase_order_id).first()
    if po is not None:
        recompute_invoiced(po)
    db.session.commit()
    return jsonify(_detail(record, match))


@match_bp.delete("/invoices/<eid>/override")
@api_or_login_required
@require_permission(APPROVALS_ACT)
def withdraw_override(eid):
    """Withdraw an acceptance, putting the invoice back among the exceptions."""
    record = _invoice(eid)
    if record is None:
        return jsonify({"error": "Invoice not found."}), 404
    match = scoped(InvoiceMatch).filter(InvoiceMatch.extraction_id == eid).first()
    if match is None or not match.is_overridden:
        return jsonify({"error": "This invoice has no accepted discrepancies.",
                        "code": "NOT_OVERRIDDEN"}), 409

    match.override_note = None
    match.overridden_by_user_id = None
    match.overridden_at = None
    db.session.commit()
    return jsonify(_detail(record, match))


# ─── From the order's side ───────────────────────────────────────────────────
@match_bp.get("/purchase-orders/<po_id>/invoices")
@api_or_login_required
@require_permission(PURCHASE_ORDERS_READ)
def invoices_for_order(po_id):
    """Every invoice billed against one order, and what is left on it.

    `remaining` counts confirmed invoices only, which is the same rule the
    comparison engine uses — a suggestion nobody has looked at must not consume
    an order's value.
    """
    po = scoped(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if po is None:
        return jsonify({"error": "Purchase order not found."}), 404

    rows = (
        db.session.query(InvoiceMatch, Extraction)
        .join(Extraction, Extraction.id == InvoiceMatch.extraction_id)
        .filter(
            InvoiceMatch.purchase_order_id == po.id,
            InvoiceMatch.organization_id == po.organization_id,
            Extraction.deleted_at.is_(None),
        )
        .order_by(Extraction.created_at.desc())
        .limit(MAX_PAGE_SIZE)
        .all()
    )

    cache = {}
    invoiced = to_decimal("0")
    items = []
    for match, record in rows:
        if match.status == InvoiceMatch.CONFIRMED and record.total is not None:
            invoiced += to_decimal(record.total) or to_decimal("0")
        items.append({
            "matchId": match.id,
            "extractionId": record.id,
            "fileName": record.file_name,
            "invoiceNumber": record.invoice_number,
            "invoiceDate": record.invoice_date,
            "currency": record.currency,
            "total": as_json(record.total),
            "status": match.status,
            "method": match.method,
            "outcome": match.outcome,
            "blockingCount": match.blocking_count or 0,
            "reviewCount": match.review_count or 0,
            "overridden": match.is_overridden,
            "overrideNote": match.override_note,
            "overriddenBy": _user_label(match.overridden_by_user_id, cache),
        })

    po_total = to_decimal(po.total) or to_decimal("0")
    return jsonify({
        "purchaseOrderId": po.id,
        "poNumber": po.po_number,
        "currency": po.currency,
        "poTotal": as_json(po_total),
        "invoiced": as_json(invoiced),
        "remaining": as_json(po_total - invoiced),
        "items": items,
    })
