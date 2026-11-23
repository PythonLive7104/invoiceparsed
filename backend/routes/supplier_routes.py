"""Supplier management.

Bank details are gated separately from the rest of the record. They are the
highest-value target in the dataset — invoice-redirection fraud works by
changing them — so `suppliers:read` gets the supplier and
`suppliers:bank:read` gets the payment instructions. Unauthorized callers do
not receive the key at all, rather than receiving it empty: a nulled field
still confirms the details exist.
"""
import logging

from flask import Blueprint, jsonify, request

from auth import api_or_login_required
from extensions import db
from models import Extraction, Supplier
from roles import (
    SUPPLIER_BANK_READ,
    SUPPLIERS_READ,
    SUPPLIERS_WRITE,
)
from suppliers import (
    match_key_for,
    possible_duplicate_suppliers,
    supplier_stats,
)
from tenancy import current_organization, has_permission, require_permission, scoped

supplier_bp = Blueprint("suppliers", __name__, url_prefix="/api/suppliers")
logger = logging.getLogger(__name__)

MAX_PAGE_SIZE = 100

# Fields a client may set. Anything else is ignored rather than rejected, so an
# older frontend sending an extra key keeps working.
EDITABLE = {
    "contactName": "contact_name",
    "email": "email",
    "phone": "phone",
    "address": "address",
    "country": "country",
    "taxId": "tax_id",
    "registrationNumber": "registration_number",
    "paymentTerms": "payment_terms",
    "currency": "currency",
    "notes": "notes",
    "status": "status",
}

BANK_FIELDS = {
    "bankName": "bank_name",
    "accountName": "bank_account_name",
    "accountNumber": "bank_account_number",
    "iban": "bank_iban",
    "swift": "bank_swift",
    "sortCode": "bank_sort_code",
}


def _can_see_bank() -> bool:
    return has_permission(SUPPLIER_BANK_READ)


def _validate(data, supplier) -> dict:
    """Apply the editable fields, returning {field: message} for any rejected."""
    errors = {}

    if "name" in data:
        name = (data.get("name") or "").strip()
        key = match_key_for(name)
        if not name:
            errors["name"] = "A supplier needs a name."
        elif not key:
            errors["name"] = "That name has nothing to match on."
        else:
            clash = Supplier.query.filter(
                Supplier.organization_id == supplier.organization_id,
                Supplier.match_key == key,
                Supplier.id != supplier.id,
            ).first()
            if clash is not None:
                errors["name"] = f"'{clash.name}' already exists and would be the same supplier."
            else:
                supplier.name = name[:200]
                supplier.match_key = key[:200]

    for payload_key, column in EDITABLE.items():
        if payload_key not in data:
            continue
        value = data.get(payload_key)
        value = value.strip() if isinstance(value, str) else value

        if payload_key == "country" and value:
            value = value.upper()
            if len(value) != 2:
                errors["country"] = "Use a two-letter country code, e.g. NG."
                continue
        if payload_key == "currency" and value:
            value = value.upper()
            if not (len(value) == 3 and value.isalpha()):
                errors["currency"] = "Use a three-letter currency code, e.g. NGN."
                continue
        if payload_key == "status" and value not in ("active", "archived"):
            errors["status"] = "Status must be 'active' or 'archived'."
            continue

        setattr(supplier, column, value or None)

    return errors


@supplier_bp.get("")
@api_or_login_required
@require_permission(SUPPLIERS_READ)
def list_suppliers():
    query = scoped(Supplier)

    text = (request.args.get("q") or "").strip()
    if text:
        like = f"%{text}%"
        query = query.filter(
            db.or_(
                Supplier.name.ilike(like),
                Supplier.email.ilike(like),
                Supplier.tax_id.ilike(like),
            )
        )

    status = (request.args.get("status") or "active").strip()
    if status in ("active", "archived"):
        query = query.filter(Supplier.status == status)
    # status=all falls through unfiltered.

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
        query.order_by(Supplier.name.asc())
        .limit(per_page)
        .offset((page - 1) * per_page)
        .all()
    )

    # Invoice counts for the whole page in one query.
    counts = dict(
        db.session.query(Extraction.supplier_id, db.func.count(Extraction.id))
        .filter(
            Extraction.supplier_id.in_([r.id for r in rows] or [""]),
            Extraction.deleted_at.is_(None),
        )
        .group_by(Extraction.supplier_id)
        .all()
    )

    return jsonify({
        "suppliers": [
            {**r.public(), "invoiceCount": counts.get(r.id, 0)} for r in rows
        ],
        "page": page,
        "perPage": per_page,
        "total": total,
        "pages": max(1, (total + per_page - 1) // per_page),
    })


@supplier_bp.post("")
@api_or_login_required
@require_permission(SUPPLIERS_WRITE)
def create_supplier():
    data = request.get_json(silent=True) or {}
    organization = current_organization()

    supplier = Supplier(organization_id=organization.id, name="", match_key="")
    if "name" not in data:
        return jsonify({"error": "A supplier needs a name.",
                        "fields": {"name": "Required."}}), 400

    errors = _validate(data, supplier)
    if "bankDetails" in data:
        bank_errors = _apply_bank(supplier, data)
        errors.update(bank_errors)
    if errors:
        return jsonify({"error": "Some details need fixing.", "fields": errors}), 400

    db.session.add(supplier)
    db.session.commit()
    return jsonify({"supplier": supplier.public(include_bank=_can_see_bank())}), 201


@supplier_bp.get("/duplicates")
@api_or_login_required
@require_permission(SUPPLIERS_READ)
def duplicate_suppliers():
    """Suppliers that may be the same business recorded twice."""
    organization = current_organization()
    return jsonify({"duplicates": possible_duplicate_suppliers(organization.id)})


@supplier_bp.get("/<sid>")
@api_or_login_required
@require_permission(SUPPLIERS_READ)
def get_supplier(sid):
    supplier = scoped(Supplier).filter(Supplier.id == sid).first()
    if supplier is None:
        return jsonify({"error": "Supplier not found."}), 404
    return jsonify({
        "supplier": supplier.public(
            include_bank=_can_see_bank(), stats=supplier_stats(supplier)
        )
    })


@supplier_bp.get("/<sid>/invoices")
@api_or_login_required
@require_permission(SUPPLIERS_READ)
def supplier_invoices(sid):
    supplier = scoped(Supplier).filter(Supplier.id == sid).first()
    if supplier is None:
        return jsonify({"error": "Supplier not found."}), 404

    rows = (
        scoped(Extraction)
        .filter(
            Extraction.supplier_id == supplier.id,
            Extraction.deleted_at.is_(None),
        )
        .order_by(Extraction.created_at.desc())
        .limit(200)
        .all()
    )
    return jsonify({"invoices": [r.list_item() for r in rows]})


@supplier_bp.patch("/<sid>")
@api_or_login_required
@require_permission(SUPPLIERS_WRITE)
def update_supplier(sid):
    supplier = scoped(Supplier).filter(Supplier.id == sid).first()
    if supplier is None:
        return jsonify({"error": "Supplier not found."}), 404

    data = request.get_json(silent=True) or {}
    errors = _validate(data, supplier)

    if "bankDetails" in data:
        # Changing payment instructions is the single most abusable edit here,
        # so it needs the bank permission even though the rest of the record
        # only needs suppliers:write.
        if not _can_see_bank():
            return jsonify({
                "error": "Your role cannot change payment details.",
                "code": "FORBIDDEN",
                "required": SUPPLIER_BANK_READ,
            }), 403
        errors.update(_apply_bank(supplier, data))

    if errors:
        return jsonify({"error": "Some details need fixing.", "fields": errors}), 400

    db.session.commit()
    return jsonify({
        "supplier": supplier.public(
            include_bank=_can_see_bank(), stats=supplier_stats(supplier)
        )
    })


def _apply_bank(supplier, data) -> dict:
    bank = data.get("bankDetails")
    if bank is None:
        for column in BANK_FIELDS.values():
            setattr(supplier, column, None)
        return {}
    if not isinstance(bank, dict):
        return {"bankDetails": "Expected an object of payment details."}
    for payload_key, column in BANK_FIELDS.items():
        if payload_key in bank:
            value = bank.get(payload_key)
            value = value.strip() if isinstance(value, str) else value
            setattr(supplier, column, value or None)
    return {}


@supplier_bp.delete("/<sid>")
@api_or_login_required
@require_permission(SUPPLIERS_WRITE)
def archive_supplier(sid):
    """Archive a supplier. Deliberately not a delete.

    A supplier with invoices against it cannot be removed without orphaning
    financial history, and history is the thing this product exists to keep.
    """
    supplier = scoped(Supplier).filter(Supplier.id == sid).first()
    if supplier is None:
        return jsonify({"error": "Supplier not found."}), 404
    supplier.status = "archived"
    db.session.commit()
    return jsonify({"supplier": supplier.public(include_bank=_can_see_bank())})
