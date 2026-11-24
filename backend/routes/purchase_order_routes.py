"""Purchase orders.

The commitment side of accounts payable: what the organization agreed to buy,
from whom, at what price. P2.3 and P2.4 match incoming invoices and goods
receipts against these records, so the integrity rules here are not cosmetic.

Three things this layer refuses to do:

* **Trust a total.** Totals always come from the lines (`purchase_orders.
  recompute_totals`). A client cannot state what an order is worth.
* **Let an approved order change.** Commercial terms are editable in `draft`
  only. Approval approves specific amounts; to change them you cancel and raise
  a new order.
* **Delete anything.** Cancelling is the strongest action available. An order
  that was approved is financial history even once abandoned.

Approving is gated on `approvals:act`, separately from `purchase_orders:write`,
so the person who raises an order is not automatically the person who can
authorize it.
"""
import logging
import mimetypes
import os

from flask import Blueprint, current_app, g, jsonify, request, send_file
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

from auth import api_or_login_required
from config import Config
from extensions import db
from models import PurchaseOrder, PurchaseOrderAttachment, Supplier, User
from money import as_json
from plans import PAYABLES, PAYABLES_FEATURE
from purchase_orders import (
    TransitionError,
    next_po_number,
    replace_lines,
    transition,
    validate_lines,
)
from roles import (
    APPROVALS_ACT,
    PURCHASE_ORDERS_READ,
    PURCHASE_ORDERS_WRITE,
)
from tenancy import (
    current_organization,
    require_capability,
    require_permission,
    scoped,
)

purchase_order_bp = Blueprint("purchase_orders", __name__,
                              url_prefix="/api/purchase-orders")
logger = logging.getLogger(__name__)

MAX_PAGE_SIZE = 100
NUMBER_RETRIES = 5

ALLOWED_ATTACHMENT_MIME = {
    "application/pdf", "image/jpeg", "image/jpg", "image/png",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel", "text/csv", "text/plain",
}
ALLOWED_ATTACHMENT_EXT = (
    ".pdf", ".jpg", ".jpeg", ".png", ".xlsx", ".xls", ".csv", ".txt",
)
MAX_ATTACHMENTS = 20

# Plain text fields a client may set, mapped to their columns. Anything not
# listed is ignored rather than rejected, so an older frontend sending an extra
# key keeps working.
EDITABLE = {
    "orderDate": "order_date",
    "expectedDeliveryDate": "expected_delivery_date",
    "paymentTerms": "payment_terms",
    "deliveryAddress": "delivery_address",
    "notes": "notes",
    "reference": "reference",
    "department": "department",
    "costCenter": "cost_center",
    "project": "project",
    "category": "category",
}
MAX_LENGTHS = {
    "order_date": 40, "expected_delivery_date": 40, "payment_terms": 120,
    "delivery_address": 500, "notes": 20000, "reference": 120,
    "department": 120, "cost_center": 120, "project": 120, "category": 120,
}


# ─── Helpers ─────────────────────────────────────────────────────────────────
def _attachment_dir(po_id: str) -> str:
    return os.path.join(Config.UPLOAD_DIR, "po", po_id)


def _load(po_id: str) -> PurchaseOrder | None:
    return scoped(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()


def _user_label(user_id: str | None) -> dict | None:
    """A minimal identity for display. Name and email only — enough to say who
    approved something without handing the client a whole user record."""
    if not user_id:
        return None
    user = User.query.get(user_id)
    if user is None:
        return None
    return {"id": user.id, "name": user.name, "email": user.email}


def _detail(po: PurchaseOrder):
    supplier = Supplier.query.get(po.supplier_id) if po.supplier_id else None
    return jsonify({
        "purchaseOrder": po.public(
            # Payment details are deliberately absent: a PO is about what was
            # ordered, and bank details are gated behind suppliers:bank:read on
            # the supplier endpoints. Embedding them here would route around
            # that check.
            supplier=supplier.public() if supplier else None,
            created_by=_user_label(po.created_by_user_id),
            approved_by=_user_label(po.approved_by_user_id),
        )
    })


def _apply_fields(po: PurchaseOrder, data: dict) -> dict:
    """Apply scalar fields. Returns {field: message} for anything rejected."""
    errors: dict[str, str] = {}

    if "currency" in data:
        value = (data.get("currency") or "").strip().upper()
        if not (len(value) == 3 and value.isalpha()):
            errors["currency"] = "Use a three-letter currency code, e.g. NGN."
        else:
            po.currency = value

    if "poNumber" in data:
        number = (data.get("poNumber") or "").strip()
        if not number:
            errors["poNumber"] = "A PO number cannot be blank."
        elif len(number) > 60:
            errors["poNumber"] = "That PO number is too long."
        else:
            # On an edit, exclude this order from the clash check. On a create
            # po.id is still None, so there is nothing to exclude - spelled out
            # rather than leaning on SQLAlchemy rendering `id != None` as
            # `id IS NOT NULL`, which happens to be right here and would be
            # easy to "tidy up" into something that is not.
            query = PurchaseOrder.query.filter(
                PurchaseOrder.organization_id == po.organization_id,
                PurchaseOrder.po_number == number,
            )
            if po.id is not None:
                query = query.filter(PurchaseOrder.id != po.id)
            clash = query.first()
            if clash is not None:
                errors["poNumber"] = f"{number} is already used by another order."
            else:
                po.po_number = number

    for payload_key, column in EDITABLE.items():
        if payload_key not in data:
            continue
        value = data.get(payload_key)
        if isinstance(value, str):
            value = value.strip()[:MAX_LENGTHS[column]]
        setattr(po, column, value or None)

    return errors


def _resolve_supplier(organization_id: str, supplier_id) -> tuple[Supplier | None, str | None]:
    if not supplier_id:
        return None, "Choose the supplier this order goes to."
    supplier = Supplier.query.filter(
        Supplier.id == supplier_id,
        Supplier.organization_id == organization_id,
    ).first()
    if supplier is None:
        return None, "That supplier does not exist."
    if supplier.status == "archived":
        # Refused when assigning a supplier to an order: you should not raise a
        # fresh commitment against a vendor someone has deliberately retired.
        # Orders already pointing at a now-archived supplier are untouched -
        # archiving must not break history.
        return supplier, "That supplier is archived. Restore it first to order from it."
    return supplier, None


# ─── List and summary ────────────────────────────────────────────────────────
@purchase_order_bp.get("")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(PURCHASE_ORDERS_READ)
def list_purchase_orders():
    query = scoped(PurchaseOrder)

    status = (request.args.get("status") or "").strip()
    if status == "open":
        query = query.filter(PurchaseOrder.status.in_(sorted(PurchaseOrder.OPEN_STATUSES)))
    elif status in PurchaseOrder.STATUSES:
        query = query.filter(PurchaseOrder.status == status)

    supplier_id = (request.args.get("supplierId") or "").strip()
    if supplier_id:
        query = query.filter(PurchaseOrder.supplier_id == supplier_id)

    text = (request.args.get("q") or "").strip()
    if text:
        like = f"%{text}%"
        query = query.filter(db.or_(
            PurchaseOrder.po_number.ilike(like),
            PurchaseOrder.reference.ilike(like),
        ))

    try:
        page = max(1, int(request.args.get("page") or 1))
    except ValueError:
        page = 1
    try:
        per_page = int(request.args.get("perPage") or 25)
    except ValueError:
        per_page = 25
    per_page = max(1, min(per_page, MAX_PAGE_SIZE))

    total = query.order_by(None).count()
    rows = (
        query.order_by(PurchaseOrder.created_at.desc())
        .limit(per_page)
        .offset((page - 1) * per_page)
        .all()
    )

    # Supplier names for the whole page in one query rather than per row.
    names = dict(
        db.session.query(Supplier.id, Supplier.name)
        .filter(Supplier.id.in_([r.supplier_id for r in rows] or [""]))
        .all()
    )

    return jsonify({
        "purchaseOrders": [
            r.list_item(supplier_name=names.get(r.supplier_id)) for r in rows
        ],
        "page": page,
        "perPage": per_page,
        "total": total,
        "pages": max(1, (total + per_page - 1) // per_page),
    })


@purchase_order_bp.get("/summary")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(PURCHASE_ORDERS_READ)
def summary():
    """Counts by status, and open commitment per currency.

    Per currency and never summed across them: one figure spanning USD and NGN
    is a meaningless number that looks authoritative.
    """
    organization = current_organization()

    counts = dict(
        db.session.query(PurchaseOrder.status, db.func.count(PurchaseOrder.id))
        .filter(PurchaseOrder.organization_id == organization.id)
        .group_by(PurchaseOrder.status)
        .all()
    )

    rows = (
        db.session.query(
            PurchaseOrder.currency,
            # type_ stated explicitly: without it the aggregate can come back
            # from the driver as a float, and a float is exactly what the
            # Numeric columns exist to avoid. Stated here, SQLAlchemy hands
            # back a Decimal whatever the database is.
            db.func.sum(PurchaseOrder.total, type_=db.Numeric(18, 4)),
            db.func.count(PurchaseOrder.id),
        )
        .filter(
            PurchaseOrder.organization_id == organization.id,
            PurchaseOrder.status.in_(sorted(PurchaseOrder.OPEN_STATUSES)),
        )
        .group_by(PurchaseOrder.currency)
        .all()
    )

    return jsonify({
        "counts": {status: counts.get(status, 0) for status in PurchaseOrder.STATUSES},
        "awaitingApproval": counts.get(PurchaseOrder.PENDING_APPROVAL, 0),
        "openCommitment": [
            {"currency": currency, "total": as_json(total), "count": count}
            for currency, total, count in rows
        ],
    })


# ─── Create, read, update ────────────────────────────────────────────────────
@purchase_order_bp.post("")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(PURCHASE_ORDERS_WRITE)
def create_purchase_order():
    data = request.get_json(silent=True) or {}
    organization = current_organization()

    supplier, supplier_error = _resolve_supplier(organization.id, data.get("supplierId"))
    if supplier_error:
        return jsonify({"error": supplier_error,
                        "fields": {"supplierId": supplier_error}}), 400

    clean_lines, line_errors = validate_lines(data.get("lines"))

    po = PurchaseOrder(
        organization_id=organization.id,
        supplier_id=supplier.id,
        created_by_user_id=g.user.id,
        status=PurchaseOrder.DRAFT,
        # The supplier's own currency and terms are the sensible defaults; they
        # are what the invoice will arrive in.
        currency=(supplier.currency or "USD").upper(),
        payment_terms=supplier.payment_terms,
    )
    errors = _apply_fields(po, data)
    errors.update(line_errors)
    if errors:
        return jsonify({"error": "Some details need fixing.", "fields": errors}), 400

    replace_lines(po, clean_lines)

    # A client-supplied number is honoured; otherwise generate one. Two
    # simultaneous creates can pick the same number, so retry on the unique
    # constraint rather than locking a counter on every create.
    client_number = bool((data.get("poNumber") or "").strip())
    for attempt in range(NUMBER_RETRIES):
        if not client_number:
            po.po_number = next_po_number(organization.id)
        db.session.add(po)
        try:
            db.session.commit()
            break
        except IntegrityError:
            db.session.rollback()
            if client_number:
                return jsonify({
                    "error": "That PO number is already in use.",
                    "fields": {"poNumber": "Already in use."},
                }), 409
            if attempt == NUMBER_RETRIES - 1:
                logger.exception("could not allocate a PO number for org %s",
                                 organization.id)
                return jsonify({
                    "error": "Could not allocate a PO number. Please try again.",
                }), 503

    return _detail(po), 201


@purchase_order_bp.get("/<po_id>")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(PURCHASE_ORDERS_READ)
def get_purchase_order(po_id):
    po = _load(po_id)
    if po is None:
        return jsonify({"error": "Purchase order not found."}), 404
    return _detail(po)


@purchase_order_bp.patch("/<po_id>")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(PURCHASE_ORDERS_WRITE)
def update_purchase_order(po_id):
    po = _load(po_id)
    if po is None:
        return jsonify({"error": "Purchase order not found."}), 404

    data = request.get_json(silent=True) or {}

    if not po.is_editable:
        # The central integrity rule. An approved order is a record of what was
        # authorized at specific amounts; editing it afterwards would make the
        # approval a signature on a document that no longer exists.
        return jsonify({
            "error": (
                f"This order is {po.status.replace('_', ' ')} and can no longer "
                "be edited. Cancel it and raise a new order to change what was "
                "ordered."
            ),
            "code": "NOT_EDITABLE",
        }), 409

    errors = {}
    if "supplierId" in data and data.get("supplierId") != po.supplier_id:
        supplier, supplier_error = _resolve_supplier(
            po.organization_id, data.get("supplierId")
        )
        if supplier_error:
            errors["supplierId"] = supplier_error
        else:
            po.supplier_id = supplier.id

    errors.update(_apply_fields(po, data))

    replace = "lines" in data
    clean_lines: list = []
    if replace:
        clean_lines, line_errors = validate_lines(data.get("lines"))
        errors.update(line_errors)

    if errors:
        db.session.rollback()
        return jsonify({"error": "Some details need fixing.", "fields": errors}), 400

    if replace:
        replace_lines(po, clean_lines)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "That PO number is already in use.",
                        "fields": {"poNumber": "Already in use."}}), 409
    return _detail(po)


# ─── Lifecycle ───────────────────────────────────────────────────────────────
def _transition_response(po: PurchaseOrder, status: str, *, reason=None):
    try:
        transition(po, status, user_id=g.user.id, reason=reason)
    except TransitionError as exc:
        db.session.rollback()
        # 409: the request is well-formed, the order's state forbids it.
        return jsonify({"error": exc.message, "code": exc.code}), 409
    db.session.commit()
    return _detail(po)


@purchase_order_bp.post("/<po_id>/submit")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(PURCHASE_ORDERS_WRITE)
def submit_purchase_order(po_id):
    """Send a draft for approval."""
    po = _load(po_id)
    if po is None:
        return jsonify({"error": "Purchase order not found."}), 404
    return _transition_response(po, PurchaseOrder.PENDING_APPROVAL)


@purchase_order_bp.post("/<po_id>/approve")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(APPROVALS_ACT)
def approve_purchase_order(po_id):
    """Authorize the order.

    Gated on approvals:act rather than purchase_orders:write, so raising an
    order and authorizing it are separate capabilities. `transition` also
    refuses self-approval where another approver exists.
    """
    po = _load(po_id)
    if po is None:
        return jsonify({"error": "Purchase order not found."}), 404
    return _transition_response(po, PurchaseOrder.APPROVED)


@purchase_order_bp.post("/<po_id>/reject")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(APPROVALS_ACT)
def reject_purchase_order(po_id):
    """Send the order back to draft with a reason."""
    po = _load(po_id)
    if po is None:
        return jsonify({"error": "Purchase order not found."}), 404

    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    if not reason:
        # A rejection without a reason gives the person correcting the order
        # nothing to act on, and leaves no record of why money was refused.
        return jsonify({
            "error": "Say why you are rejecting this order.",
            "fields": {"reason": "Required."},
        }), 400
    return _transition_response(po, PurchaseOrder.DRAFT, reason=reason)


@purchase_order_bp.post("/<po_id>/status")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(PURCHASE_ORDERS_WRITE)
def set_status(po_id):
    """Move the order along its lifecycle: sent, received, closed, cancelled.

    Approval moves are not available here — they have their own endpoints and
    their own permission, so this cannot be used to approve an order.
    """
    po = _load(po_id)
    if po is None:
        return jsonify({"error": "Purchase order not found."}), 404

    status = ((request.get_json(silent=True) or {}).get("status") or "").strip()
    if status in (PurchaseOrder.APPROVED, PurchaseOrder.PENDING_APPROVAL):
        return jsonify({
            "error": "Use the approval endpoints to submit or approve an order.",
            "code": "WRONG_ENDPOINT",
        }), 400
    return _transition_response(po, status)


@purchase_order_bp.delete("/<po_id>")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(PURCHASE_ORDERS_WRITE)
def cancel_purchase_order(po_id):
    """Cancel an order. Deliberately not a delete.

    An order that was approved is a record of money the organization committed
    to spend. Abandoning it does not make that untrue, and an invoice may still
    arrive against it.
    """
    po = _load(po_id)
    if po is None:
        return jsonify({"error": "Purchase order not found."}), 404
    return _transition_response(po, PurchaseOrder.CANCELLED)


# ─── PDF ─────────────────────────────────────────────────────────────────────
@purchase_order_bp.get("/<po_id>/pdf")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(PURCHASE_ORDERS_READ)
def purchase_order_pdf(po_id):
    po = _load(po_id)
    if po is None:
        return jsonify({"error": "Purchase order not found."}), 404

    from po_pdf import render_purchase_order

    supplier = Supplier.query.get(po.supplier_id) if po.supplier_id else None
    try:
        pdf = render_purchase_order(
            po, organization=current_organization(), supplier=supplier
        )
    except RuntimeError as exc:
        # reportlab missing on this server. A clear 503 beats a 500 traceback.
        logger.error("PDF rendering unavailable: %s", exc)
        return jsonify({"error": str(exc), "code": "PDF_UNAVAILABLE"}), 503
    except Exception:
        logger.exception("failed to render PDF for purchase order %s", po.id)
        return jsonify({"error": "Could not generate that PDF."}), 500

    filename = f"{po.po_number or 'purchase-order'}.pdf".replace("/", "-")
    response = current_app.response_class(pdf, mimetype="application/pdf")
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.headers["Content-Length"] = str(len(pdf))
    return response


# ─── Attachments ─────────────────────────────────────────────────────────────
@purchase_order_bp.post("/<po_id>/attachments")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(PURCHASE_ORDERS_WRITE)
def add_attachment(po_id):
    """Attach a quote, spec or signed copy.

    Allowed after approval, unlike edits: an attachment is evidence about the
    order rather than a term of it, so adding one cannot change what was
    agreed. Cancelled orders are closed to new files.
    """
    po = _load(po_id)
    if po is None:
        return jsonify({"error": "Purchase order not found."}), 404
    if po.status == PurchaseOrder.CANCELLED:
        return jsonify({"error": "This order is cancelled.",
                        "code": "NOT_EDITABLE"}), 409
    if len(po.attachments) >= MAX_ATTACHMENTS:
        return jsonify({
            "error": f"An order can hold at most {MAX_ATTACHMENTS} attachments.",
        }), 400

    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return jsonify({"error": "No file was uploaded."}), 400

    payload = uploaded.read()
    if not payload:
        return jsonify({"error": f"'{uploaded.filename}' is empty."}), 400
    if len(payload) > Config.MAX_FILE_BYTES:
        return jsonify({"error": f"'{uploaded.filename}' exceeds the 10MB limit."}), 413

    mime = uploaded.mimetype or "application/octet-stream"
    lowered = uploaded.filename.lower()
    if mime not in ALLOWED_ATTACHMENT_MIME and not lowered.endswith(ALLOWED_ATTACHMENT_EXT):
        return jsonify({
            "error": f"'{uploaded.filename}' is not an accepted file type.",
        }), 415

    attachment = PurchaseOrderAttachment(
        purchase_order_id=po.id,
        organization_id=po.organization_id,
        uploaded_by_user_id=g.user.id,
        file_name=uploaded.filename[:255],
        file_type=mime[:100],
        file_size=len(payload),
        stored_name="",
    )
    db.session.add(attachment)
    db.session.flush()   # need the id for the stored name

    # secure_filename strips any path the client sent; the id prefix keeps two
    # files of the same name apart. Nothing from the client reaches the path.
    safe = secure_filename(uploaded.filename) or "attachment"
    attachment.stored_name = f"{attachment.id}__{safe}"[:255]

    directory = _attachment_dir(po.id)
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, attachment.stored_name), "wb") as handle:
        handle.write(payload)

    db.session.commit()
    return jsonify({"attachment": attachment.public()}), 201


@purchase_order_bp.get("/<po_id>/attachments/<attachment_id>")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(PURCHASE_ORDERS_READ)
def get_attachment(po_id, attachment_id):
    po = _load(po_id)
    if po is None:
        return jsonify({"error": "Purchase order not found."}), 404

    attachment = next(
        (a for a in po.attachments if a.id == attachment_id), None
    )
    if attachment is None:
        return jsonify({"error": "Attachment not found."}), 404

    # The path is rebuilt from the order id and the stored name, both of which
    # the server wrote. basename() is belt-and-braces against a legacy row.
    path = os.path.join(_attachment_dir(po.id),
                        os.path.basename(attachment.stored_name))
    if not os.path.isfile(path):
        return jsonify({"error": "That file is no longer stored."}), 404

    mime = attachment.file_type or (
        mimetypes.guess_type(attachment.file_name)[0] or "application/octet-stream"
    )
    return send_file(path, mimetype=mime, download_name=attachment.file_name)


@purchase_order_bp.delete("/<po_id>/attachments/<attachment_id>")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(PURCHASE_ORDERS_WRITE)
def delete_attachment(po_id, attachment_id):
    po = _load(po_id)
    if po is None:
        return jsonify({"error": "Purchase order not found."}), 404

    attachment = next(
        (a for a in po.attachments if a.id == attachment_id), None
    )
    if attachment is None:
        return jsonify({"error": "Attachment not found."}), 404

    path = os.path.join(_attachment_dir(po.id),
                        os.path.basename(attachment.stored_name))
    db.session.delete(attachment)
    db.session.commit()
    try:
        os.remove(path)
    except OSError:
        # The row is gone, which is what the client asked for. A file we cannot
        # unlink is a housekeeping problem, not a failed request.
        logger.warning("could not remove attachment file %s", path)
    return jsonify({"ok": True})
