"""Extraction endpoints: extract, list, get, update, delete, CSV, original files."""
import json
import mimetypes
import os
import shutil

from flask import Blueprint, Response, current_app, g, jsonify, request, send_file
from werkzeug.utils import secure_filename

from auth import api_or_login_required
from config import Config
from csv_util import invoice_to_csv
from extensions import db
from invoice_schema import normalize
from models import Extraction, User
from openai_service import extract_invoice
from plans import build_usage, plan_allows, start_of_month
from webhooks import dispatch

extract_bp = Blueprint("extract", __name__, url_prefix="/api")

ALLOWED_MIME = {"application/pdf", "image/jpeg", "image/jpg", "image/png"}
ALLOWED_EXT = (".pdf", ".jpg", ".jpeg", ".png")


def _count_usage(user: User) -> int:
    return (
        Extraction.query.filter(
            Extraction.user_id == user.id,
            Extraction.status == "completed",
            Extraction.created_at >= start_of_month(),
        ).count()
    )


# ─── Original-file storage ───────────────────────────────────────────────────
def _extraction_dir(eid: str) -> str:
    return os.path.join(Config.UPLOAD_DIR, eid)


def _save_files(eid: str, pages: list[dict]) -> None:
    d = _extraction_dir(eid)
    os.makedirs(d, exist_ok=True)
    for i, p in enumerate(pages):
        safe = secure_filename(p["name"]) or f"page{i}"
        with open(os.path.join(d, f"{i}__{safe}"), "wb") as fh:
            fh.write(p["bytes"])


def _list_files(eid: str) -> list[dict]:
    d = _extraction_dir(eid)
    if not os.path.isdir(d):
        return []
    out = []
    for fn in os.listdir(d):
        idx, sep, orig = fn.partition("__")
        if not sep or not idx.isdigit():
            continue
        mime = mimetypes.guess_type(orig)[0] or "application/octet-stream"
        out.append({"index": int(idx), "name": orig, "mime": mime})
    out.sort(key=lambda x: x["index"])
    return out


def _serialize(row: Extraction, invoice) -> dict:
    return {
        "id": row.id,
        "fileName": row.file_name,
        "fileType": row.file_type,
        "fileSize": row.file_size,
        "status": row.status,
        "createdAt": row.created_at.isoformat() + "Z",
        "invoice": invoice,
        "files": _list_files(row.id),
    }


def _apply_headline_fields(row: Extraction, invoice: dict) -> None:
    row.vendor_name = (invoice.get("vendor") or {}).get("name")
    row.invoice_number = invoice.get("invoice_number")
    row.invoice_date = invoice.get("invoice_date")
    row.due_date = invoice.get("due_date")
    row.currency = invoice.get("currency")
    row.total = invoice.get("total")
    row.data = json.dumps(invoice)


# ─── Extraction ──────────────────────────────────────────────────────────────
@extract_bp.post("/extract")
@api_or_login_required
def extract():
    user = g.user

    # Enforce plan limits before spending an API call.
    usage = build_usage(_count_usage(user), user.plan)
    if usage["atLimit"]:
        return (
            jsonify({
                "error": f"You've reached your {usage['planName']} plan limit of "
                         f"{usage['limit']} invoices this month.",
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

    mode = (request.form.get("mode") or "single").lower()

    if mode == "batch" and not plan_allows(user.plan, "batch"):
        return (
            jsonify({
                "error": "Batch upload is available on paid plans. Upgrade to process invoices in bulk.",
                "code": "UPGRADE_REQUIRED",
                "capability": "batch",
            }),
            402,
        )

    if len(files) > 1 and not plan_allows(user.plan, "multiPage"):
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

    try:
        invoice = extract_invoice(pages)
    except Exception as exc:  # noqa: BLE001 — surface a clean message to the client
        failed = Extraction(
            user_id=user.id,
            file_name=display_name,
            file_type=primary["mime"],
            file_size=total_size,
            data=json.dumps({"error": str(exc)}),
            status="failed",
        )
        db.session.add(failed)
        db.session.commit()
        return jsonify({"error": f"Extraction failed: {exc}"}), 502

    record = Extraction(
        user_id=user.id,
        file_name=display_name,
        file_type=primary["mime"],
        file_size=total_size,
        status="completed",
    )
    _apply_headline_fields(record, invoice)
    db.session.add(record)
    db.session.commit()

    # Persist the originals so they can be viewed later.
    _save_files(record.id, pages)

    payload = _serialize(record, invoice)

    # Fire webhooks (background thread; never blocks the response).
    dispatch(
        current_app._get_current_object(),
        user.id,
        "extraction.completed",
        payload,
    )

    return jsonify({**payload, "usage": build_usage(_count_usage(user), user.plan)})


@extract_bp.get("/extractions")
@api_or_login_required
def list_extractions():
    rows = (
        Extraction.query.filter_by(user_id=g.user.id)
        .order_by(Extraction.created_at.desc())
        .limit(300)
        .all()
    )
    return jsonify({"extractions": [r.list_item() for r in rows]})


@extract_bp.get("/extractions/<eid>")
@api_or_login_required
def get_extraction(eid):
    row = Extraction.query.filter_by(id=eid, user_id=g.user.id).first()
    if row is None:
        return jsonify({"error": "Extraction not found."}), 404
    try:
        invoice = json.loads(row.data)
    except json.JSONDecodeError:
        invoice = None
    return jsonify(_serialize(row, invoice))


@extract_bp.patch("/extractions/<eid>")
@api_or_login_required
def update_extraction(eid):
    """Persist user (or API) edits to an extraction's fields."""
    row = Extraction.query.filter_by(id=eid, user_id=g.user.id).first()
    if row is None or row.status != "completed":
        return jsonify({"error": "Extraction not found."}), 404

    body = request.get_json(silent=True) or {}
    inv = body.get("invoice")
    if not isinstance(inv, dict):
        return jsonify({"error": "Expected an 'invoice' object."}), 400

    invoice = normalize(inv)
    _apply_headline_fields(row, invoice)
    db.session.commit()
    return jsonify(_serialize(row, invoice))


@extract_bp.delete("/extractions/<eid>")
@api_or_login_required
def delete_extraction(eid):
    row = Extraction.query.filter_by(id=eid, user_id=g.user.id).first()
    if row is None:
        return jsonify({"error": "Extraction not found."}), 404
    db.session.delete(row)
    db.session.commit()
    shutil.rmtree(_extraction_dir(eid), ignore_errors=True)
    return jsonify({"success": True})


# ─── Original document files ─────────────────────────────────────────────────
@extract_bp.get("/extractions/<eid>/files")
@api_or_login_required
def list_extraction_files(eid):
    row = Extraction.query.filter_by(id=eid, user_id=g.user.id).first()
    if row is None:
        return jsonify({"error": "Extraction not found."}), 404
    return jsonify({"files": _list_files(eid)})


@extract_bp.get("/extractions/<eid>/file/<int:index>")
@api_or_login_required
def get_extraction_file(eid, index):
    row = Extraction.query.filter_by(id=eid, user_id=g.user.id).first()
    if row is None:
        return jsonify({"error": "Extraction not found."}), 404
    d = _extraction_dir(eid)
    if os.path.isdir(d):
        for fn in os.listdir(d):
            if fn.startswith(f"{index}__"):
                mime = mimetypes.guess_type(fn)[0] or "application/octet-stream"
                return send_file(os.path.join(d, fn), mimetype=mime)
    return jsonify({"error": "File not found."}), 404


@extract_bp.get("/extractions/<eid>/csv")
@api_or_login_required
def download_csv(eid):
    row = Extraction.query.filter_by(id=eid, user_id=g.user.id).first()
    if row is None or row.status != "completed":
        return jsonify({"error": "Extraction not found."}), 404

    invoice = json.loads(row.data)
    csv_text = invoice_to_csv(invoice)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (row.invoice_number or row.vendor_name or row.id))
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{safe}.csv"'},
    )
