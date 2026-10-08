"""Try-before-signup: let a visitor extract one document with no account.

The conversion mechanic: a visitor drops an invoice on the landing page and sees
the real extracted result immediately. Exports are gated behind signup, and the
result is held server-side under a single-use claim token so creating an account
adopts the extraction instead of making them upload it again.

Abuse control is two-layer: a durable per-IP lifetime cap (DemoUsage, keyed by a
salted hash of the address) plus a burst rate limit on the endpoint.
"""
import hashlib
import json
import os
import secrets
import shutil
from datetime import datetime, timedelta

from flask import Blueprint, current_app, g, jsonify, request

from auth import login_required
from documents import apply_headline_fields, extraction_dir, list_files, save_files
from extensions import db, limiter
from models import DemoExtraction, DemoUsage, Extraction
from openai_service import extract_document
from usage import usage_for

demo_bp = Blueprint("demo", __name__, url_prefix="/api/demo")

# Statements are deliberately excluded: they're the costliest document type to
# extract and the slowest to return, which is wrong for an unauthenticated demo.
DEMO_DOC_TYPES = ("invoice", "receipt")

ALLOWED_MIME = {"application/pdf", "image/jpeg", "image/jpg", "image/png"}
ALLOWED_EXT = (".pdf", ".jpg", ".jpeg", ".png")


def _ip_hash() -> str:
    """Salted hash of the caller's IP. ProxyFix has already resolved the real
    client address from X-Forwarded-For (see PROXY_HOPS)."""
    raw = f"{current_app.config['JWT_SECRET']}:{request.remote_addr or 'unknown'}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _used(ip_hash: str) -> int:
    row = db.session.get(DemoUsage, ip_hash)
    return row.count if row else 0


def _purge_expired() -> None:
    """Drop demo results (and their files) past the retention window, claimed or
    not. Runs opportunistically on demo requests — no scheduler needed."""
    cutoff = datetime.utcnow() - timedelta(hours=current_app.config["DEMO_RETENTION_HOURS"])
    stale = DemoExtraction.query.filter(DemoExtraction.created_at < cutoff).all()
    for row in stale:
        shutil.rmtree(extraction_dir(row.id), ignore_errors=True)
        db.session.delete(row)
    if stale:
        db.session.commit()


def _status_payload(ip_hash: str) -> dict:
    used = _used(ip_hash)
    limit = current_app.config["DEMO_FREE_EXTRACTIONS"]
    return {
        "enabled": bool(
            current_app.config["DEMO_ENABLED"] and current_app.config["OPENAI_API_KEY"]
        ),
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used),
        "docTypes": list(DEMO_DOC_TYPES),
    }


@demo_bp.get("/status")
def status():
    """Whether this visitor still has a free demo extraction left."""
    return jsonify(_status_payload(_ip_hash()))


@demo_bp.post("/extract")
@limiter.limit(lambda: current_app.config["RATELIMIT_DEMO"])
def demo_extract():
    if not current_app.config["DEMO_ENABLED"]:
        return jsonify({"error": "The demo is currently unavailable.", "code": "DEMO_DISABLED"}), 403
    if not current_app.config["OPENAI_API_KEY"]:
        return jsonify({"error": "Extraction is not configured.", "code": "DEMO_DISABLED"}), 503

    ip_hash = _ip_hash()
    _purge_expired()

    limit = current_app.config["DEMO_FREE_EXTRACTIONS"]
    if _used(ip_hash) >= limit:
        return (
            jsonify({
                "error": f"You've used your {limit} free extraction"
                         f"{'s' if limit != 1 else ''}. Create a free account to keep going — "
                         "5 more documents a month, no card required.",
                "code": "DEMO_LIMIT_REACHED",
                "demo": _status_payload(ip_hash),
            }),
            402,
        )

    # One file only — the demo is a taste, not a workflow. Batch and multi-page
    # stay paid capabilities behind the dashboard.
    files = [f for f in request.files.getlist("file") if f and f.filename]
    if not files:
        return jsonify({"error": "No file provided."}), 400
    if len(files) > 1:
        return (
            jsonify({
                "error": "The demo handles one file at a time. Sign up to batch-upload "
                         "or combine multi-page documents.",
                "code": "DEMO_SINGLE_FILE",
            }),
            400,
        )

    doc_type = (request.form.get("doc_type") or "invoice").lower()
    if doc_type not in DEMO_DOC_TYPES:
        doc_type = "invoice"

    f = files[0]
    data = f.read()
    if len(data) == 0:
        return jsonify({"error": f"'{f.filename}' is empty."}), 400
    if len(data) > current_app.config["MAX_FILE_BYTES"]:
        return jsonify({"error": f"'{f.filename}' exceeds the 10MB limit."}), 413
    mime = f.mimetype or "application/octet-stream"
    if mime not in ALLOWED_MIME and not f.filename.lower().endswith(ALLOWED_EXT):
        return jsonify({"error": f"'{f.filename}' is not a PDF, JPG, or PNG."}), 415

    pages = [{"bytes": data, "mime": mime, "name": f.filename}]

    # Count the attempt before spending the API call, so a failed-but-expensive
    # call can't be retried for free in a loop.
    row = db.session.get(DemoUsage, ip_hash)
    if row is None:
        row = DemoUsage(ip_hash=ip_hash, count=0)
        db.session.add(row)
    row.count += 1
    row.last_at = datetime.utcnow()
    db.session.commit()

    try:
        document = extract_document(pages, doc_type)
    except Exception as exc:  # noqa: BLE001 — surface a clean message to the client
        return jsonify({"error": f"Extraction failed: {exc}"}), 502

    record = DemoExtraction(
        ip_hash=ip_hash,
        claim_token=secrets.token_urlsafe(32),
        doc_type=doc_type,
        file_name=f.filename,
        file_type=mime,
        file_size=len(data),
        data=json.dumps(document),
    )
    db.session.add(record)
    db.session.commit()
    save_files(record.id, pages)

    return jsonify({
        "id": record.id,
        "claimToken": record.claim_token,
        "docType": record.doc_type,
        "fileName": record.file_name,
        "invoice": document,
        "demo": _status_payload(ip_hash),
    })


@demo_bp.post("/claim")
@login_required
def claim():
    """Adopt a demo extraction into the now-signed-in user's account.

    Idempotent from the client's point of view: an unknown, already-claimed or
    expired token is reported as nothing-to-claim rather than an error, since the
    browser fires this on every sign-in while a token is held.
    """
    body = request.get_json(silent=True) or {}
    token = (body.get("token") or "").strip()
    if not token:
        return jsonify({"claimed": False, "reason": "no_token"}), 200

    row = DemoExtraction.query.filter_by(claim_token=token, claimed_at=None).first()
    if row is None:
        return jsonify({"claimed": False, "reason": "not_found"}), 200

    record = Extraction(
        user_id=g.user.id,
        doc_type=row.doc_type,
        file_name=row.file_name,
        file_type=row.file_type,
        file_size=row.file_size,
        data="{}",
        status="completed",
    )
    apply_headline_fields(record, json.loads(row.data))
    db.session.add(record)
    row.claimed_at = datetime.utcnow()
    db.session.commit()

    # Hand the stored original over to the real extraction so the document
    # viewer works on it exactly like any other upload.
    src, dst = extraction_dir(row.id), extraction_dir(record.id)
    if os.path.isdir(src) and not os.path.exists(dst):
        try:
            shutil.move(src, dst)
        except OSError:
            pass  # the record is still valid without the original file

    return jsonify({
        "claimed": True,
        "extraction": {
            "id": record.id,
            "docType": record.doc_type,
            "fileName": record.file_name,
            "invoice": json.loads(row.data),
            "files": list_files(record.id),
        },
        "usage": usage_for(g.user),
    })
