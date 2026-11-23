"""Extraction endpoints: extract, list, get, update, delete, CSV, original files."""
import csv
import io
import json
import mimetypes
import os
import shutil
import time
from datetime import datetime, timedelta

from flask import Blueprint, Response, current_app, g, jsonify, request, send_file

import duplicates as dup
from auth import api_or_login_required, rate_limit_key
from config import Config
from csv_util import invoice_to_csv, receipt_to_csv, statement_to_csv
from documents import (
    apply_headline_fields,
    extraction_dir,
    list_files,
    load_document,
    normalize_for,
    save_files,
)
from extensions import db, limiter
from models import (
    DuplicateMatch,
    Extraction,
    FieldCorrection,
    InvoiceMatch,
    PurchaseOrder,
    User,
)
from money import as_json, to_decimal
from openai_service import extract_document
from plans import plan_allows
from po_matching import auto_match, evaluate
from roles import DOCUMENTS_EXPORT, DOCUMENTS_WRITE
from suppliers import attach_to_invoice
from tenancy import current_organization, require_permission, scoped
from usage import usage_for
from validation import validate_invoice
from webhooks import dispatch
from xlsx_util import document_to_xlsx

extract_bp = Blueprint("extract", __name__, url_prefix="/api")

ALLOWED_MIME = {"application/pdf", "image/jpeg", "image/jpg", "image/png"}
ALLOWED_EXT = (".pdf", ".jpg", ".jpeg", ".png")
DOC_TYPES = ("invoice", "receipt", "statement")

_CSV_WRITERS = {"invoice": invoice_to_csv, "receipt": receipt_to_csv, "statement": statement_to_csv}


def _safe_name(row) -> str:
    """Filesystem-safe base name for an export download."""
    raw = row.invoice_number or row.vendor_name or row.id
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in raw)


# Fields whose changes are worth recording. The confidence block is the
# model's own scoring, not user data, so edits never touch it.
_AUDIT_SKIP = {"confidence"}


def _flatten(data, prefix="") -> dict:
    """Flatten a document into {dotted.path: scalar} for comparison.

    Lists are indexed, so "line_items.2.unit_price" identifies one cell on one
    line rather than reporting that "line_items changed".
    """
    flat = {}
    if isinstance(data, dict):
        for key, value in data.items():
            if key in _AUDIT_SKIP:
                continue
            flat.update(_flatten(value, f"{prefix}{key}."))
    elif isinstance(data, list):
        for index, value in enumerate(data):
            flat.update(_flatten(value, f"{prefix}{index}."))
    else:
        flat[prefix.rstrip(".")] = data
    return flat


def _as_text(value):
    """Render a value for the audit row. None stays None so an emptied field is
    distinguishable from one set to the string 'None'."""
    if value is None:
        return None
    return str(value)[:500]


def _record_corrections(row, before, after, *, user_id, reason=None) -> list:
    """Persist every field a person changed.

    The ORIGINAL value is kept forever: correcting a figure must never destroy
    the evidence of what the document said before someone touched it. These
    rows are also the only honest record of where extraction gets things wrong.
    """
    old_flat, new_flat = _flatten(before), _flatten(after)
    corrections = []
    for path in sorted(set(old_flat) | set(new_flat)):
        old_value, new_value = old_flat.get(path), new_flat.get(path)
        if old_value == new_value:
            continue
        # Treat None and "" as the same absence, so re-saving an untouched form
        # does not manufacture a trail of phantom edits.
        if (old_value in (None, "")) and (new_value in (None, "")):
            continue
        correction = FieldCorrection(
            organization_id=row.organization_id,
            extraction_id=row.id,
            user_id=user_id,
            field_path=path[:120],
            old_value=_as_text(old_value),
            new_value=_as_text(new_value),
            reason=reason,
        )
        db.session.add(correction)
        corrections.append(correction)
    return corrections


def _corrections_for(extraction_id) -> list:
    rows = (
        scoped(FieldCorrection)
        .filter(FieldCorrection.extraction_id == extraction_id)
        .order_by(FieldCorrection.created_at.desc())
        .limit(200)
        .all()
    )
    labels = _uploader_names_by_id({r.user_id for r in rows})
    return [r.public(user_label=labels.get(r.user_id)) for r in rows]


def _uploader_names_by_id(ids) -> dict:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {
        u.id: (u.name or u.email) for u in User.query.filter(User.id.in_(ids)).all()
    }


def _count_filled(data) -> int:
    """How many fields the extractor actually filled.

    Nested objects count their own filled children rather than counting as one,
    so a vendor block with five details is a better read than one with a name.
    """
    if not isinstance(data, dict):
        return 0
    filled = 0
    for key, value in data.items():
        if key == "confidence":
            continue
        if isinstance(value, dict):
            filled += _count_filled(value)
        elif isinstance(value, list):
            filled += sum(_count_filled(v) for v in value if isinstance(v, dict))
        elif value not in (None, "", []):
            filled += 1
    return filled


def _record_processing_stats(row: Extraction, data, *, elapsed_ms=None) -> None:
    """Denormalize what the history list needs to filter and sort on.

    Validation is still recomputed from the document on read, so an edited
    invoice always shows a current verdict; this stores the last known one so
    the list can answer "show me everything needing review" in SQL instead of
    loading and validating every row.
    """
    if elapsed_ms is not None:
        row.processing_ms = int(elapsed_ms)
    row.extracted_field_count = _count_filled(data)
    if row.doc_type == "invoice" and isinstance(data, dict):
        verdict = validate_invoice(data)
        row.validation_status = verdict["status"]
        row.validation_issue_count = verdict["issueCount"]
    else:
        row.validation_status = None
        row.validation_issue_count = 0


def _serialize(row: Extraction, data) -> dict:
    payload = {
        "id": row.id,
        "docType": row.doc_type,
        "fileName": row.file_name,
        "fileType": row.file_type,
        "fileSize": row.file_size,
        "status": row.status,
        "createdAt": row.created_at.isoformat() + "Z",
        "invoice": data,  # the extracted document (invoice or receipt shape)
        "files": list_files(row.id),
    }
    # Validation is computed on read rather than stored. It is a pure function
    # of the document, so recomputing keeps it correct after a user edits a
    # field - a stored verdict would go stale the moment someone fixes a total.
    if row.doc_type == "invoice" and isinstance(data, dict):
        payload["validation"] = validate_invoice(data)
    payload["duplicates"] = _duplicates_for(row.id)
    payload["corrections"] = _corrections_for(row.id)
    if row.doc_type == "invoice" and isinstance(data, dict):
        # Recomputed from the live document, like validation above, so an
        # edited figure changes the verdict immediately. `evaluate` refreshes
        # the cached columns the exception list filters on; the caller commits.
        payload["poMatch"] = _po_match_for(row, data)
    return payload


def _po_match_for(row, data) -> dict | None:
    """Where this invoice stands against its purchase order, or None.

    None rather than an empty comparison when the organization has no purchase
    orders at all: a product being used only for extraction should not start
    reporting "no PO reference" exceptions on every document.
    """
    has_orders = (
        db.session.query(PurchaseOrder.id)
        .filter(PurchaseOrder.organization_id == row.organization_id)
        .first()
    )
    match = InvoiceMatch.query.filter_by(extraction_id=row.id).first()
    if has_orders is None and match is None:
        return None
    comparison = evaluate(row, data, match=match)
    # `evaluate` refreshed the cached verdict on the match row, and this is the
    # last thing that happens before the response is built, so it is committed
    # here rather than left for a caller to remember. Without it, correcting a
    # figure on an invoice would change what the detail page shows and leave
    # the exception list filtering on the old answer.
    db.session.commit()
    return {
        "matchId": match.id if match else None,
        "purchaseOrderId": match.purchase_order_id if match else None,
        "status": match.status if match else None,
        "method": match.method if match else None,
        "outcome": comparison.get("outcome"),
        "blocked": comparison.get("blocked", False),
        "overridden": bool(match and match.is_overridden),
        "counts": comparison.get("counts"),
        "findings": comparison.get("findings"),
    }


# ─── Extraction ──────────────────────────────────────────────────────────────
@extract_bp.post("/extract")
@limiter.limit(
    lambda: current_app.config["RATELIMIT_EXTRACT"],
    key_func=rate_limit_key,
)
@api_or_login_required
def extract():
    user = g.user
    organization = current_organization()

    # Plan limits are the ORGANIZATION's, so a team shares one allowance.
    usage = usage_for(organization)
    if usage["atLimit"]:
        return (
            jsonify({
                "error": f"You've reached your {usage['planName']} plan limit of "
                         f"{usage['limit']} documents this month.",
                "code": "LIMIT_REACHED",
                "usage": usage,
            }),
            402,
        )

    # One request may carry several files. A single file is a normal extraction;
    # multiple files are treated as the pages of ONE invoice (multi-page) — a
    # paid-only capability. The client also tags batch uploads with mode=batch
    # (one request per invoice) so we can gate that capability server-side.
    files = [f for f in request.files.getlist("file") if f and f.filename]
    if not files:
        return jsonify({"error": "No file provided."}), 400

    # Every page rides along in the same model request, so the page count is a
    # direct multiplier on what this one call costs. Cap it before reading any
    # bytes, independent of the request body cap.
    if len(files) > Config.MAX_PAGES_PER_DOC:
        return (
            jsonify({
                "error": f"A document may have at most {Config.MAX_PAGES_PER_DOC} "
                         f"pages per request (received {len(files)}).",
                "code": "TOO_MANY_PAGES",
            }),
            413,
        )

    doc_type = (request.form.get("doc_type") or "invoice").lower()
    if doc_type not in DOC_TYPES:
        doc_type = "invoice"

    # Bank statements are a Business-plan capability with their own monthly
    # allowance (they're far costlier to extract than invoices/receipts).
    if doc_type == "statement":
        if not plan_allows(organization.plan, "statements"):
            return (
                jsonify({
                    "error": "Bank statement extraction is a Business-plan feature.",
                    "code": "UPGRADE_REQUIRED",
                    "capability": "statements",
                }),
                402,
            )
        stmt = usage["statements"]
        if stmt["atLimit"]:
            return (
                jsonify({
                    "error": f"You've used all {stmt['limit']} bank statements included "
                             f"in your {usage['planName']} plan this month.",
                    "code": "LIMIT_REACHED",
                    "capability": "statements",
                    "usage": usage,
                }),
                402,
            )

    mode = (request.form.get("mode") or "single").lower()

    if mode == "batch" and not plan_allows(organization.plan, "batch"):
        return (
            jsonify({
                "error": "Batch upload is available on paid plans. Upgrade to process invoices in bulk.",
                "code": "UPGRADE_REQUIRED",
                "capability": "batch",
            }),
            402,
        )

    if len(files) > 1 and not plan_allows(organization.plan, "multiPage"):
        return (
            jsonify({
                "error": "Multi-page invoices are available on paid plans. Upgrade to combine pages.",
                "code": "UPGRADE_REQUIRED",
                "capability": "multiPage",
            }),
            402,
        )

    pages = []
    total_size = 0
    for f in files:
        data = f.read()
        size = len(data)
        if size == 0:
            return jsonify({"error": f"'{f.filename}' is empty."}), 400
        if size > Config.MAX_FILE_BYTES:
            return jsonify({"error": f"'{f.filename}' exceeds the 10MB limit."}), 413
        mime = f.mimetype or "application/octet-stream"
        if mime not in ALLOWED_MIME and not f.filename.lower().endswith(ALLOWED_EXT):
            return jsonify({"error": f"'{f.filename}' is not a PDF, JPG, or PNG."}), 415
        pages.append({"bytes": data, "mime": mime, "name": f.filename})
        total_size += size

    primary = pages[0]
    display_name = (
        primary["name"] if len(pages) == 1 else f"{primary['name']} (+{len(pages) - 1} pages)"
    )

    # Create a "processing" record up front so the job is tracked in History even
    # if the user navigates away during a long extraction (e.g. a big statement).
    record = Extraction(
        organization_id=organization.id,
        user_id=user.id,
        doc_type=doc_type,
        file_name=display_name,
        file_type=primary["mime"],
        file_size=total_size,
        # Hashed before extraction: an identical re-upload is a duplicate
        # regardless of what the model makes of it this time.
        file_hash=dup.file_hash(pages),
        data="{}",
        status="processing",
    )
    db.session.add(record)
    db.session.commit()
    save_files(record.id, pages)  # store originals now so the viewer works regardless

    started = time.monotonic()
    try:
        document = extract_document(pages, doc_type)
    except Exception as exc:  # noqa: BLE001 — surface a clean message to the client
        record.status = "failed"
        record.processing_ms = int((time.monotonic() - started) * 1000)
        # Kept in its own column so History can show WHY without the client
        # having to parse the stored payload.
        record.error_message = str(exc)[:500]
        record.data = json.dumps({"error": str(exc)})
        db.session.commit()
        return jsonify({"error": f"Extraction failed: {exc}"}), 502

    record.status = "completed"
    record.error_message = None
    apply_headline_fields(record, document)
    # Attach to a supplier (creating one if this is a new vendor) so the
    # document counts toward that supplier's history straight away.
    try:
        attach_to_invoice(record, organization.id, document)
    except Exception:
        # Never lose a processed document over supplier bookkeeping.
        db.session.rollback()
        current_app.logger.exception(
            "Supplier attach failed for extraction %s", record.id
        )
    _record_processing_stats(
        record, document, elapsed_ms=(time.monotonic() - started) * 1000
    )
    db.session.commit()

    # After the headline fields are set, so supplier/number/amount comparisons
    # have something to work with. Never blocks the upload: a detection failure
    # must not lose a document the customer has already paid to process.
    try:
        _record_duplicates(record, organization.id)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Duplicate detection failed for extraction %s", record.id
        )

    # Match against an open purchase order. After the supplier is attached, so
    # a supplier-and-amount suggestion has something to work with. Never blocks
    # the upload for the same reason duplicate detection does not: the customer
    # has already paid to process this document, and a matching failure must
    # not be what loses it.
    try:
        auto_match(record, document)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "PO matching failed for extraction %s", record.id
        )

    payload = _serialize(record, document)

    # Fire webhooks (background thread; never blocks the response).
    dispatch(
        current_app._get_current_object(),
        organization.id,
        "extraction.completed",
        payload,
    )

    return jsonify({**payload, "usage": usage_for(organization)})


def _record_duplicates(record, organization_id) -> list:
    """Find and persist suspected duplicates for a freshly completed upload."""
    found = dup.find_duplicates(record, organization_id=organization_id)
    rows = []
    for match in found:
        existing = DuplicateMatch.query.filter_by(
            extraction_id=record.id,
            duplicate_of_id=match["other"].id,
            reason=match["reason"],
        ).first()
        if existing is not None:
            rows.append(existing)
            continue
        row = DuplicateMatch(
            organization_id=organization_id,
            extraction_id=record.id,
            duplicate_of_id=match["other"].id,
            reason=match["reason"],
            score=match["score"],
            detail=match["detail"],
        )
        db.session.add(row)
        rows.append(row)
    return rows


def _duplicates_for(extraction_id):
    """Unresolved matches for an extraction, with the document each points at.

    Dismissed matches are excluded: once someone has said "these are two
    genuine invoices", re-showing the warning teaches people to ignore it.
    """
    rows = (
        scoped(DuplicateMatch)
        .filter(
            DuplicateMatch.extraction_id == extraction_id,
            DuplicateMatch.status != "dismissed",
        )
        .order_by(DuplicateMatch.score.desc())
        .all()
    )
    out = []
    for row in rows:
        other = Extraction.query.filter_by(id=row.duplicate_of_id).first()
        if other is None or other.deleted_at is not None:
            continue  # the document it pointed at is gone
        out.append(row.public(other))
    return out


@extract_bp.post("/extractions/<eid>/duplicates/<mid>")
@api_or_login_required
@require_permission(DOCUMENTS_WRITE)
def resolve_duplicate(eid, mid):
    """Confirm or dismiss a suspected duplicate.

    Deliberately does not delete anything on "confirmed". Marking the match is
    the record of the decision; what happens to the document afterwards is the
    user's call, and an automatic delete would destroy evidence of a real
    double-billing attempt.
    """
    row = scoped(DuplicateMatch).filter(
        DuplicateMatch.id == mid, DuplicateMatch.extraction_id == eid
    ).first()
    if row is None:
        return jsonify({"error": "Duplicate match not found."}), 404

    body = request.get_json(silent=True) or {}
    decision = (body.get("status") or "").lower()
    if decision not in ("confirmed", "dismissed"):
        return jsonify({
            "error": "Set status to 'confirmed' or 'dismissed'.",
            "code": "INVALID_STATUS",
        }), 400

    row.status = decision
    row.resolved_by_user_id = g.user.id
    row.resolved_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"duplicate": row.public(), "duplicates": _duplicates_for(eid)})


@extract_bp.get("/duplicates")
@api_or_login_required
def list_duplicates():
    """Every unresolved suspected duplicate in the organization, for review."""
    rows = (
        scoped(DuplicateMatch)
        .filter(DuplicateMatch.status == "pending")
        .order_by(DuplicateMatch.score.desc(), DuplicateMatch.created_at.desc())
        .limit(200)
        .all()
    )
    out = []
    for row in rows:
        subject = Extraction.query.filter_by(id=row.extraction_id).first()
        other = Extraction.query.filter_by(id=row.duplicate_of_id).first()
        if subject is None or other is None:
            continue
        if subject.deleted_at is not None or other.deleted_at is not None:
            continue
        entry = row.public(other)
        entry["extraction"] = subject.list_item()
        out.append(entry)
    return jsonify({"duplicates": out})


# Columns the list may be sorted by. An allow-list, because the value arrives
# from the query string and feeds straight into ORDER BY.
_SORTABLE = {
    "createdAt": Extraction.created_at,
    "total": Extraction.total,
    "vendorName": Extraction.vendor_name,
    "invoiceDate": Extraction.invoice_date,
    "status": Extraction.status,
    "validationStatus": Extraction.validation_status,
}

MAX_PAGE_SIZE = 100


def _apply_history_filters(query, args):
    """Narrow the history query from the request's query string.

    Every filter is optional and ignores a blank value, so the frontend can send
    the whole filter object without pruning it first.
    """
    text = (args.get("q") or "").strip()
    if text:
        like = f"%{text}%"
        query = query.filter(
            db.or_(
                Extraction.file_name.ilike(like),
                Extraction.vendor_name.ilike(like),
                Extraction.invoice_number.ilike(like),
            )
        )

    doc_type = (args.get("docType") or "").strip()
    if doc_type in DOC_TYPES:
        query = query.filter(Extraction.doc_type == doc_type)

    status = (args.get("status") or "").strip()
    if status:
        query = query.filter(Extraction.status == status)

    validation = (args.get("validationStatus") or "").strip()
    if validation:
        query = query.filter(Extraction.validation_status == validation)

    vendor = (args.get("vendor") or "").strip()
    if vendor:
        query = query.filter(Extraction.vendor_name.ilike(f"%{vendor}%"))

    currency = (args.get("currency") or "").strip()
    if currency:
        query = query.filter(Extraction.currency == currency.upper())

    reviewed = (args.get("reviewed") or "").strip().lower()
    if reviewed == "true":
        query = query.filter(Extraction.reviewed_at.isnot(None))
    elif reviewed == "false":
        query = query.filter(Extraction.reviewed_at.is_(None))

    # Dates are compared against created_at (when it was processed), which is
    # what "show me last week's uploads" means.
    date_from = _parse_day(args.get("dateFrom"))
    if date_from:
        query = query.filter(Extraction.created_at >= date_from)
    date_to = _parse_day(args.get("dateTo"))
    if date_to:
        # Inclusive of the whole day the user picked.
        query = query.filter(Extraction.created_at < date_to + timedelta(days=1))

    amount_min = to_decimal(args.get("amountMin"))
    if amount_min is not None:
        query = query.filter(Extraction.total >= amount_min)
    amount_max = to_decimal(args.get("amountMax"))
    if amount_max is not None:
        query = query.filter(Extraction.total <= amount_max)

    return query


def _parse_day(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


@extract_bp.get("/extractions")
@api_or_login_required
def list_extractions():
    """Processing history: filtered, searchable and paginated.

    Replaces a flat 300-row cap, which silently hid everything older once an
    organization had processed a few hundred documents.
    """
    args = request.args
    query = _apply_history_filters(
        scoped(Extraction).filter(Extraction.deleted_at.is_(None)), args
    )

    sort_key = args.get("sort") or "createdAt"
    column = _SORTABLE.get(sort_key, Extraction.created_at)
    descending = (args.get("order") or "desc").lower() != "asc"
    query = query.order_by(column.desc() if descending else column.asc())

    try:
        page = max(1, int(args.get("page") or 1))
    except ValueError:
        page = 1
    try:
        per_page = int(args.get("perPage") or 25)
    except ValueError:
        per_page = 25
    per_page = max(1, min(per_page, MAX_PAGE_SIZE))

    total = query.order_by(None).count()
    rows = query.limit(per_page).offset((page - 1) * per_page).all()

    # Uploader names and duplicate counts in two queries rather than one per
    # row - this list is the most-hit endpoint in the app.
    uploaders = _uploader_names(rows)
    dup_counts = _duplicate_counts(rows)

    return jsonify({
        "extractions": [
            r.list_item(
                uploader=uploaders.get(r.user_id),
                duplicate_count=dup_counts.get(r.id, 0),
            )
            for r in rows
        ],
        "page": page,
        "perPage": per_page,
        "total": total,
        "pages": max(1, (total + per_page - 1) // per_page),
    })


def _uploader_names(rows) -> dict:
    ids = {r.user_id for r in rows if r.user_id}
    if not ids:
        return {}
    users = User.query.filter(User.id.in_(ids)).all()
    return {u.id: (u.name or u.email) for u in users}


def _duplicate_counts(rows) -> dict:
    ids = [r.id for r in rows]
    if not ids:
        return {}
    pairs = (
        db.session.query(DuplicateMatch.extraction_id, db.func.count(DuplicateMatch.id))
        .filter(
            DuplicateMatch.extraction_id.in_(ids),
            DuplicateMatch.status == "pending",
        )
        .group_by(DuplicateMatch.extraction_id)
        .all()
    )
    return dict(pairs)


@extract_bp.get("/extractions/export")
@api_or_login_required
@require_permission(DOCUMENTS_EXPORT)
def export_history():
    """Download the CURRENT filtered history as CSV.

    The same filters as the list, so what you see is what you export. Capped at
    a sane number of rows: this is a processing report, not a bulk data dump,
    and the per-document CSV export already exists for the detail.
    """
    query = _apply_history_filters(
        scoped(Extraction).filter(Extraction.deleted_at.is_(None)), request.args
    )
    rows = query.order_by(Extraction.created_at.desc()).limit(5000).all()
    uploaders = _uploader_names(rows)
    dup_counts = _duplicate_counts(rows)

    headers = [
        "Uploaded", "Document", "Type", "Supplier", "Invoice No", "Invoice Date",
        "Currency", "Total", "Processing", "Validation", "Issues", "Duplicates",
        "Fields", "Processing ms", "Error", "Reviewed", "Uploaded By",
    ]
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(headers)
    for r in rows:
        writer.writerow([
            r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
            r.file_name, r.doc_type, r.vendor_name or "", r.invoice_number or "",
            r.invoice_date or "", r.currency or "",
            as_json(r.total) or "", r.status, r.validation_status or "",
            r.validation_issue_count or 0, dup_counts.get(r.id, 0),
            r.extracted_field_count or 0, r.processing_ms or "",
            r.error_message or "", "yes" if r.reviewed_at else "no",
            uploaders.get(r.user_id, ""),
        ])
    return Response(
        out.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": 'attachment; filename="processing-history.csv"'},
    )


@extract_bp.get("/extractions/<eid>")
@api_or_login_required
def get_extraction(eid):
    row = scoped(Extraction).filter(Extraction.id == eid, Extraction.deleted_at.is_(None)).first()
    if row is None:
        return jsonify({"error": "Extraction not found."}), 404
    return jsonify(_serialize(row, load_document(row)))


@extract_bp.patch("/extractions/<eid>")
@api_or_login_required
def update_extraction(eid):
    """Persist user (or API) edits to an extraction's fields."""
    row = scoped(Extraction).filter(Extraction.id == eid, Extraction.deleted_at.is_(None)).first()
    if row is None or row.status != "completed":
        return jsonify({"error": "Extraction not found."}), 404

    body = request.get_json(silent=True) or {}
    inv = body.get("invoice")
    if not isinstance(inv, dict):
        return jsonify({"error": "Expected an 'invoice' object."}), 400

    before = load_document(row) or {}
    data = normalize_for(row.doc_type)(inv)

    # Diffed BEFORE the row is updated, against the normalized form of both
    # sides - so a change from 100 to "100.00" is not recorded as an edit.
    _record_corrections(
        row, before, data,
        user_id=g.user.id,
        reason=(body.get("reason") or None),
    )

    apply_headline_fields(row, data)
    _record_processing_stats(row, data)
    # An edit is a human looking at the document, which is what "reviewed" means.
    row.reviewed_at = datetime.utcnow()
    row.reviewed_by_user_id = g.user.id
    db.session.commit()
    return jsonify(_serialize(row, data))


@extract_bp.delete("/extractions/<eid>")
@api_or_login_required
def delete_extraction(eid):
    row = scoped(Extraction).filter(Extraction.id == eid, Extraction.deleted_at.is_(None)).first()
    if row is None:
        return jsonify({"error": "Extraction not found."}), 404
    # Soft delete: keep the (now file-less) row so it still counts toward monthly
    # usage — deleting history must not reset a plan or statement quota.
    row.deleted_at = datetime.utcnow()
    db.session.commit()
    shutil.rmtree(extraction_dir(eid), ignore_errors=True)
    return jsonify({"success": True})


# ─── Original document files ─────────────────────────────────────────────────
@extract_bp.get("/extractions/<eid>/files")
@api_or_login_required
def list_extraction_files(eid):
    row = scoped(Extraction).filter(Extraction.id == eid, Extraction.deleted_at.is_(None)).first()
    if row is None:
        return jsonify({"error": "Extraction not found."}), 404
    return jsonify({"files": list_files(eid)})


@extract_bp.get("/extractions/<eid>/file/<int:index>")
@api_or_login_required
def get_extraction_file(eid, index):
    row = scoped(Extraction).filter(Extraction.id == eid, Extraction.deleted_at.is_(None)).first()
    if row is None:
        return jsonify({"error": "Extraction not found."}), 404
    d = extraction_dir(eid)
    if os.path.isdir(d):
        for fn in os.listdir(d):
            if fn.startswith(f"{index}__"):
                mime = mimetypes.guess_type(fn)[0] or "application/octet-stream"
                return send_file(os.path.join(d, fn), mimetype=mime)
    return jsonify({"error": "File not found."}), 404


@extract_bp.get("/extractions/<eid>/csv")
@api_or_login_required
def download_csv(eid):
    row = scoped(Extraction).filter(Extraction.id == eid, Extraction.deleted_at.is_(None)).first()
    if row is None or row.status != "completed":
        return jsonify({"error": "Extraction not found."}), 404

    data = load_document(row)
    if data is None:
        return jsonify({"error": "Extraction not found."}), 404
    csv_text = _CSV_WRITERS.get(row.doc_type, invoice_to_csv)(data)
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{_safe_name(row)}.csv"'},
    )


@extract_bp.get("/extractions/<eid>/xlsx")
@api_or_login_required
def download_xlsx(eid):
    row = scoped(Extraction).filter(Extraction.id == eid, Extraction.deleted_at.is_(None)).first()
    if row is None or row.status != "completed":
        return jsonify({"error": "Extraction not found."}), 404

    data = load_document(row)
    if data is None:
        return jsonify({"error": "Extraction not found."}), 404
    content = document_to_xlsx(row.doc_type, data)
    return Response(
        content,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{_safe_name(row)}.xlsx"'},
    )
