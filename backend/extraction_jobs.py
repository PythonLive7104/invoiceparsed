"""The extraction pipeline, as a job.

Lifted out of `routes/extract_routes.py` so that the background worker and the
inline fallback run **exactly the same code**. Two copies of this would be two
copies of the rules about supplier attachment, duplicate detection, validation
and PO matching — and they would drift, silently, in whichever one is less
often exercised.

The job is idempotent by construction: it re-reads the row, returns early if
somebody already finished it, and reloads the pages from disk rather than
trusting anything handed to it. Re-running it is always safe, which is what
makes retries safe.
"""
import json
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)

# Terminal states. A row in one of these is nobody's work any more.
DONE = ("completed", "failed")


def run_extraction(extraction_id: str, app=None) -> str:
    """Extract one document and record everything that follows from it.

    Returns the row's final status. Takes an app for the inline path; the RQ
    worker has none and builds one, which is why `worker.py` exists.
    """
    if app is None:
        from app import create_app
        from config import Config

        app = create_app(Config)

    with app.app_context():
        return _run(extraction_id)


def _run(extraction_id: str) -> str:
    from documents import apply_headline_fields, load_pages
    from extensions import db
    from models import Extraction
    from openai_service import extract_document

    record = Extraction.query.filter_by(id=extraction_id).first()
    if record is None:
        logger.warning("extraction %s vanished before its job ran", extraction_id)
        return "missing"
    if record.status in DONE:
        # Somebody already finished it: a retry after a timeout that actually
        # succeeded, or a double-enqueue. Returning early is the whole of
        # idempotency.
        return record.status
    if record.deleted_at is not None:
        return "deleted"

    pages = load_pages(extraction_id)
    if not pages:
        return _fail(record, "The uploaded file could not be read back from "
                             "storage.")

    record.job_attempts = (record.job_attempts or 0) + 1
    db.session.commit()

    started = time.monotonic()
    try:
        document = extract_document(pages, record.doc_type)
    except Exception as exc:  # noqa: BLE001 — the message reaches the user
        elapsed = int((time.monotonic() - started) * 1000)
        return _fail(record, str(exc), elapsed_ms=elapsed)

    record.status = "completed"
    record.error_message = None
    record.processing_ms = int((time.monotonic() - started) * 1000)
    apply_headline_fields(record, document)
    db.session.commit()

    _after_extraction(record, document)
    return record.status


def _fail(record, message: str, *, elapsed_ms=None) -> str:
    """Mark a row failed, with the reason where a human will read it.

    A failed extraction does NOT consume plan quota: `usage.count_usage`
    counts only `completed` rows. That is the half of F4's acceptance criterion
    the existing design already satisfied, and it is worth not breaking.
    """
    from extensions import db

    db.session.rollback()
    record.status = "failed"
    record.error_message = (message or "Extraction failed.")[:500]
    record.data = json.dumps({"error": message})
    if elapsed_ms is not None:
        record.processing_ms = elapsed_ms
    db.session.commit()
    logger.info("extraction %s failed: %s", record.id, message)
    return "failed"


def _after_extraction(record, document) -> None:
    """Supplier, stats, duplicates, matching, webhook.

    Each step is wrapped separately and none of them can fail the extraction.
    The document is already extracted and stored; losing it over bookkeeping
    would be a far worse outcome than a missing duplicate warning, and the
    customer has already paid for the processing either way.
    """
    from extensions import db
    from plans import PAYABLES, plan_allows

    organization = _organization_of(record)

    _step(record, "supplier attach", lambda: _attach_supplier(record, document))
    _step(record, "processing stats", lambda: _record_stats(record, document))
    _step(record, "duplicate detection", lambda: _find_duplicates(record))

    if organization is not None and plan_allows(organization.plan, PAYABLES):
        _step(record, "PO matching", lambda: _match_purchase_order(record, document))

    db.session.commit()
    _dispatch_webhook(record, document)


def _step(record, label: str, action) -> None:
    from extensions import db

    try:
        action()
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("%s failed for extraction %s", label, record.id)


def _organization_of(record):
    from models import Organization

    return Organization.query.filter_by(id=record.organization_id).first()


def _attach_supplier(record, document) -> None:
    from suppliers import attach_to_invoice

    attach_to_invoice(record, record.organization_id, document)


def _record_stats(record, document) -> None:
    from validation import validate_invoice

    if record.doc_type == "invoice" and isinstance(document, dict):
        verdict = validate_invoice(document)
        record.validation_status = verdict["status"]
        record.validation_issue_count = verdict["issueCount"]
    else:
        record.validation_status = None
        record.validation_issue_count = 0
    record.extracted_field_count = _count_filled(document)


def _count_filled(data) -> int:
    """How many fields the extractor actually filled.

    Mirrors the counter the route used before this moved; a nested object
    counts its own filled leaves rather than counting as one.
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
            filled += sum(_count_filled(item) for item in value)
        elif value not in (None, "", []):
            filled += 1
    return filled


def _find_duplicates(record) -> None:
    import duplicates as dup
    from extensions import db
    from models import DuplicateMatch

    for match in dup.find_duplicates(record, organization_id=record.organization_id):
        existing = DuplicateMatch.query.filter_by(
            extraction_id=record.id,
            duplicate_of_id=match["other"].id,
            reason=match["reason"],
        ).first()
        if existing is not None:
            continue
        db.session.add(DuplicateMatch(
            organization_id=record.organization_id,
            extraction_id=record.id,
            duplicate_of_id=match["other"].id,
            reason=match["reason"],
            score=match["score"],
            detail=match["detail"],
        ))


def _match_purchase_order(record, document) -> None:
    from po_matching import auto_match

    auto_match(record, document)


def _dispatch_webhook(record, document) -> None:
    """Tell subscribers the extraction finished. Never fatal."""
    try:
        from flask import current_app

        from routes.extract_routes import _serialize
        from webhooks import dispatch

        payload = _serialize(record, document)
        dispatch(
            current_app._get_current_object(),
            record.organization_id,
            "extraction.completed",
            payload,
        )
    except Exception:
        logger.exception("webhook dispatch failed for extraction %s", record.id)


# ─── The sweeper ─────────────────────────────────────────────────────────────
def sweep_stuck(*, now=None, limit: int = 200) -> int:
    """Fail rows left in `processing` that nothing is coming back for.

    F4's acceptance criterion: `processing` is always truthful. A worker that
    is killed mid-job, a Redis that loses its queue, a deploy at the wrong
    moment — all leave a row claiming to be in progress with nothing running.
    Past `jobs.stuck_cutoff` no live job can still exist, so the row is failed
    with a message that says what happened rather than a silent dead end.

    Returns how many rows were swept. Cheap enough to call on a read path:
    the filter is indexed on `status` and bounded by `limit`.
    """
    from extensions import db
    from jobs import stuck_cutoff
    from models import Extraction

    cutoff = stuck_cutoff(now)
    stale = (
        Extraction.query.filter(
            Extraction.status == "processing",
            Extraction.deleted_at.is_(None),
            db.or_(
                db.and_(
                    Extraction.job_queued_at.isnot(None),
                    Extraction.job_queued_at < cutoff,
                ),
                db.and_(
                    Extraction.job_queued_at.is_(None),
                    Extraction.created_at < cutoff,
                ),
            ),
        )
        .limit(limit)
        .all()
    )
    for record in stale:
        record.status = "failed"
        record.error_message = (
            "Processing stopped before it finished — the server restarted or "
            "the job was lost. Upload the document again."
        )
        record.data = json.dumps({"error": "processing did not complete"})
        logger.warning("swept stuck extraction %s (queued %s)",
                       record.id, record.job_queued_at or record.created_at)
    if stale:
        db.session.commit()
    return len(stale)


def mark_queued(record, job_id: str | None) -> None:
    """Record that a row is now somebody's work, and whose."""
    record.job_id = job_id
    record.job_queued_at = datetime.utcnow()
