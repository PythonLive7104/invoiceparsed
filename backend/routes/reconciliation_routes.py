"""Bank reconciliation.

Importing statement lines and tying them to payments the organization
recorded. Gated on `reconciliation:write` for anything that changes, and on
`payments:read` for looking — reconciling is accounts work, and an accountant
holds both.

Nothing here moves money either: a reconciliation is an assertion that a
payment already recorded corresponds to a line the bank already produced.
"""
import logging

from flask import Blueprint, g, jsonify, request

from auth import api_or_login_required
from documents import load_document
from extensions import db
from models import (
    BankImport,
    BankMatch,
    BankTransaction,
    Extraction,
    SupplierPayment,
    User,
)
from money import as_json
from plans import PAYABLES, PAYABLES_FEATURE
from reconciliation import (
    MAX_ROWS,
    StatementImportError,
    candidates_for,
    confirm,
    reconciliation_summary,
    rows_from_csv,
    rows_from_statement,
    rows_from_xlsx,
    store_rows,
    suggest_for,
    suggest_for_import,
    unmatch,
)
from roles import PAYMENTS_READ, RECONCILIATION
from tenancy import (
    current_organization,
    require_capability,
    require_permission,
    scoped,
)

reconciliation_bp = Blueprint("reconciliation", __name__,
                              url_prefix="/api/reconciliation")
logger = logging.getLogger(__name__)

MAX_PAGE_SIZE = 100
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_EXT = (".csv", ".xlsx", ".xls", ".txt")


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


# ─── Importing ───────────────────────────────────────────────────────────────
@reconciliation_bp.post("/imports")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(RECONCILIATION)
def create_import():
    """Bring in a statement, from a file or from one already extracted.

    `extractionId` reuses the statement-extraction pipeline rather than
    re-reading the PDF: that document has already been parsed once, and a
    second parser would eventually disagree with the first about the same
    page.
    """
    organization = current_organization()
    body = request.get_json(silent=True) if not request.files else {}
    body = body or {}

    batch = BankImport(
        organization_id=organization.id,
        imported_by_user_id=g.user.id,
    )

    try:
        extraction_id = (body.get("extractionId") or
                         request.form.get("extractionId") or "").strip()
        if extraction_id:
            record = (
                scoped(Extraction)
                .filter(
                    Extraction.id == extraction_id,
                    Extraction.deleted_at.is_(None),
                    Extraction.doc_type == "statement",
                )
                .first()
            )
            if record is None:
                return jsonify({"error": "Statement not found."}), 404
            document = load_document(record) or {}
            rows = rows_from_statement(document)
            batch.source = BankImport.FROM_EXTRACTION
            batch.extraction_id = record.id
            batch.file_name = record.file_name
            batch.bank_name = document.get("bank_name")
            batch.account_number = document.get("account_number")
            batch.currency = document.get("currency")
            batch.period_start = document.get("period_start")
            batch.period_end = document.get("period_end")
            batch.opening_balance = document.get("opening_balance")
            batch.closing_balance = document.get("closing_balance")
        else:
            upload = request.files.get("file")
            if upload is None or not upload.filename:
                return jsonify({
                    "error": "Attach a CSV or Excel file, or name a statement "
                             "you have already extracted.",
                    "code": "NO_FILE",
                }), 400
            name = upload.filename.lower()
            if not name.endswith(ALLOWED_EXT):
                return jsonify({"error": "Upload a CSV or Excel file.",
                                "code": "BAD_TYPE"}), 400
            data = upload.read(MAX_UPLOAD_BYTES + 1)
            if len(data) > MAX_UPLOAD_BYTES:
                return jsonify({
                    "error": "That file is too large (5MB maximum).",
                    "code": "TOO_LARGE",
                }), 413

            if name.endswith((".xlsx", ".xls")):
                rows = rows_from_xlsx(data)
                batch.source = BankImport.FROM_XLSX
            else:
                # Bank exports are routinely latin-1 or cp1252; refusing a
                # statement over one accented supplier name would be absurd.
                rows = rows_from_csv(data.decode("utf-8-sig", errors="replace"))
                batch.source = BankImport.FROM_CSV
            batch.file_name = upload.filename[:255]
            batch.currency = (request.form.get("currency") or "").strip().upper() \
                or None
    except StatementImportError as exc:
        return jsonify({"error": exc.message, "code": exc.code}), 400

    if len(rows) > MAX_ROWS:
        return jsonify({
            "error": f"That statement has more than {MAX_ROWS} lines. "
                     "Split it by month and import the parts.",
            "code": "TOO_MANY_ROWS",
        }), 413

    db.session.add(batch)
    db.session.flush()
    imported, duplicates = store_rows(batch, rows)
    db.session.flush()
    suggested = suggest_for_import(batch)
    db.session.commit()

    return jsonify({
        "import": batch.public(imported_by=_user_label(g.user.id)),
        "imported": imported,
        "duplicates": duplicates,
        "suggested": suggested,
    }), 201


@reconciliation_bp.get("/imports")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(PAYMENTS_READ)
def list_imports():
    rows = (
        scoped(BankImport)
        .order_by(BankImport.created_at.desc())
        .limit(MAX_PAGE_SIZE)
        .all()
    )
    cache = {}
    return jsonify({
        "imports": [
            row.public(imported_by=_user_label(row.imported_by_user_id, cache))
            for row in rows
        ],
    })


@reconciliation_bp.delete("/imports/<import_id>")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(RECONCILIATION)
def delete_import(import_id):
    """Undo an import entirely — the statement loaded twice, or the wrong one.

    Refused once any of its lines have been reconciled: those confirmations
    are decisions somebody made, and removing the evidence underneath them
    would leave payments marked as reconciled against nothing.
    """
    batch = scoped(BankImport).filter(BankImport.id == import_id).first()
    if batch is None:
        return jsonify({"error": "Import not found."}), 404

    confirmed = (
        db.session.query(db.func.count(BankMatch.id))
        .join(BankTransaction,
              BankTransaction.id == BankMatch.bank_transaction_id)
        .filter(
            BankTransaction.bank_import_id == batch.id,
            BankMatch.status == BankMatch.CONFIRMED,
        )
        .scalar()
    ) or 0
    if confirmed:
        return jsonify({
            "error": (f"{confirmed} line"
                      f"{'' if confirmed == 1 else 's'} from this import "
                      "have been reconciled. Unmatch them first."),
            "code": "HAS_CONFIRMED_MATCHES",
        }), 409

    # Suggestions are the engine's guesses, so they go with the lines.
    for txn in batch.transactions:
        BankMatch.query.filter_by(bank_transaction_id=txn.id).delete()
    db.session.delete(batch)
    db.session.commit()
    return jsonify({"deleted": True})


# ─── The reconciliation list ─────────────────────────────────────────────────
@reconciliation_bp.get("/transactions")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(PAYMENTS_READ)
def list_transactions():
    organization = current_organization()
    page = max(1, request.args.get("page", type=int) or 1)
    size = min(MAX_PAGE_SIZE, max(1, request.args.get("perPage", type=int) or 25))

    query = scoped(BankTransaction)

    status = (request.args.get("status") or "").strip().lower()
    if status in BankTransaction.STATUSES:
        query = query.filter(BankTransaction.status == status)

    import_id = (request.args.get("importId") or "").strip()
    if import_id:
        query = query.filter(BankTransaction.bank_import_id == import_id)

    term = (request.args.get("q") or "").strip()
    if term:
        like = f"%{term}%"
        query = query.filter(
            db.or_(
                BankTransaction.description.ilike(like),
                BankTransaction.reference.ilike(like),
            )
        )

    total = query.order_by(None).count()
    rows = (
        query.order_by(BankTransaction.txn_date.desc(),
                       BankTransaction.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    matches = {}
    if rows:
        found = BankMatch.query.filter(
            BankMatch.bank_transaction_id.in_([row.id for row in rows])
        ).all()
        payments = {
            p.id: p for p in SupplierPayment.query.filter(
                SupplierPayment.id.in_([m.supplier_payment_id for m in found])
            ).all()
        } if found else {}
        cache = {}
        for match in found:
            matches[match.bank_transaction_id] = match.public(
                payment=payments.get(match.supplier_payment_id),
                confirmed_by=_user_label(match.confirmed_by_user_id, cache),
            )

    return jsonify({
        "transactions": [
            {**row.public(), "match": matches.get(row.id)} for row in rows
        ],
        "page": page,
        "perPage": size,
        "total": total,
        "pages": max(1, (total + size - 1) // size),
        "organizationId": organization.id,
    })


@reconciliation_bp.get("/summary")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(PAYMENTS_READ)
def summary():
    organization = current_organization()
    return jsonify(reconciliation_summary(organization.id))


@reconciliation_bp.get("/transactions/<txn_id>/candidates")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(PAYMENTS_READ)
def candidates(txn_id):
    """Payments this line might be, for somebody choosing by hand."""
    txn = scoped(BankTransaction).filter(BankTransaction.id == txn_id).first()
    if txn is None:
        return jsonify({"error": "Transaction not found."}), 404

    found = candidates_for(txn)
    extraction_ids = {entry["payment"].extraction_id for entry in found}
    invoices = {
        row.id: row for row in Extraction.query.filter(
            Extraction.id.in_(extraction_ids)
        ).all()
    } if extraction_ids else {}

    return jsonify({
        "transaction": txn.public(),
        "candidates": [
            {
                "paymentId": entry["payment"].id,
                "amount": as_json(entry["payment"].amount),
                "currency": entry["payment"].currency,
                "paidOn": entry["payment"].paid_on,
                "reference": entry["payment"].reference,
                "method": entry["method"],
                "score": entry["score"],
                "difference": as_json(entry["difference"]),
                "invoiceNumber": getattr(
                    invoices.get(entry["payment"].extraction_id),
                    "invoice_number", None,
                ),
                "vendorName": getattr(
                    invoices.get(entry["payment"].extraction_id),
                    "vendor_name", None,
                ),
            }
            for entry in found
        ],
    })


# ─── Matching ────────────────────────────────────────────────────────────────
@reconciliation_bp.post("/transactions/<txn_id>/match")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(RECONCILIATION)
def match_transaction(txn_id):
    """Tie a bank line to a recorded payment, confirmed.

    A person naming the payment is the strongest signal there is, so this
    confirms outright rather than leaving their own choice as a suggestion.
    """
    txn = scoped(BankTransaction).filter(BankTransaction.id == txn_id).first()
    if txn is None:
        return jsonify({"error": "Transaction not found."}), 404

    body = request.get_json(silent=True) or {}
    payment_id = (body.get("paymentId") or "").strip()
    if not payment_id:
        return jsonify({"error": "Choose a payment.",
                        "fields": {"paymentId": "Required."}}), 400

    payment = scoped(SupplierPayment).filter(
        SupplierPayment.id == payment_id
    ).first()
    if payment is None:
        return jsonify({"error": "Payment not found."}), 404
    if payment.voided_at is not None:
        return jsonify({"error": "That payment has been voided.",
                        "code": "PAYMENT_VOID"}), 409

    clash = BankMatch.query.filter(
        BankMatch.organization_id == txn.organization_id,
        BankMatch.supplier_payment_id == payment.id,
        BankMatch.status == BankMatch.CONFIRMED,
        BankMatch.bank_transaction_id != txn.id,
    ).first()
    if clash is not None:
        return jsonify({
            "error": "That payment is already reconciled against another "
                     "bank line.",
            "code": "PAYMENT_ALREADY_MATCHED",
        }), 409

    existing = BankMatch.query.filter_by(bank_transaction_id=txn.id).first()
    if existing is None:
        existing = BankMatch(
            organization_id=txn.organization_id,
            bank_transaction_id=txn.id,
            supplier_payment_id=payment.id,
        )
        db.session.add(existing)
    existing.supplier_payment_id = payment.id
    existing.method = BankMatch.BY_MANUAL
    existing.score = 1.0
    from money import to_decimal
    from reconciliation import outgoing_amount

    amount = outgoing_amount(txn)
    paid = to_decimal(payment.amount)
    existing.difference = (
        amount - paid if amount is not None and paid is not None else None
    )
    confirm(existing, g.user.id, note=(body.get("note") or "").strip() or None)
    db.session.commit()
    return jsonify({"match": existing.public(transaction=txn, payment=payment)})


@reconciliation_bp.post("/matches/<match_id>/confirm")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(RECONCILIATION)
def confirm_match(match_id):
    """Accept the engine's suggestion."""
    match = scoped(BankMatch).filter(BankMatch.id == match_id).first()
    if match is None:
        return jsonify({"error": "Match not found."}), 404
    if match.status == BankMatch.CONFIRMED:
        return jsonify({"error": "This match is already confirmed.",
                        "code": "ALREADY_CONFIRMED"}), 409

    body = request.get_json(silent=True) or {}
    confirm(match, g.user.id, note=(body.get("note") or "").strip() or None)
    db.session.commit()
    return jsonify({"match": match.public()})


@reconciliation_bp.delete("/matches/<match_id>")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(RECONCILIATION)
def remove_match(match_id):
    """Undo a match. The bank line returns to the unmatched list."""
    match = scoped(BankMatch).filter(BankMatch.id == match_id).first()
    if match is None:
        return jsonify({"error": "Match not found."}), 404
    unmatch(match)
    db.session.commit()
    return jsonify({"removed": True})


@reconciliation_bp.post("/transactions/<txn_id>/ignore")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(RECONCILIATION)
def ignore_transaction(txn_id):
    """Set a line aside with a reason.

    Bank charges, interest and transfers between an organization's own
    accounts are never going to match a supplier payment. Requiring a reason
    keeps "unmatched" a short list of real problems rather than a wall people
    stop reading — and keeps "ignored" from becoming a way to hide one.
    """
    txn = scoped(BankTransaction).filter(BankTransaction.id == txn_id).first()
    if txn is None:
        return jsonify({"error": "Transaction not found."}), 404
    if txn.status == BankTransaction.MATCHED:
        return jsonify({
            "error": "This line is reconciled. Unmatch it before ignoring it.",
            "code": "ALREADY_MATCHED",
        }), 409

    body = request.get_json(silent=True) or {}
    reason = (body.get("reason") or "").strip()
    if not reason:
        return jsonify({
            "error": "Say why this line does not need reconciling.",
            "fields": {"reason": "Required."},
            "code": "REASON_REQUIRED",
        }), 400

    txn.status = BankTransaction.IGNORED
    txn.ignore_reason = reason[:500]
    BankMatch.query.filter_by(bank_transaction_id=txn.id,
                              status=BankMatch.SUGGESTED).delete()
    db.session.commit()
    return jsonify({"transaction": txn.public()})


@reconciliation_bp.post("/transactions/<txn_id>/unignore")
@api_or_login_required
@require_capability(PAYABLES, PAYABLES_FEATURE)
@require_permission(RECONCILIATION)
def unignore_transaction(txn_id):
    txn = scoped(BankTransaction).filter(BankTransaction.id == txn_id).first()
    if txn is None:
        return jsonify({"error": "Transaction not found."}), 404
    if txn.status != BankTransaction.IGNORED:
        return jsonify({"error": "This line is not ignored.",
                        "code": "NOT_IGNORED"}), 409
    txn.status = BankTransaction.UNMATCHED
    txn.ignore_reason = None
    suggest_for(txn)
    db.session.commit()
    return jsonify({"transaction": txn.public()})
