"""Usage and processing statistics for an organization.

Everything here is a SQL aggregate rather than a Python loop over rows: these
numbers are shown on the dashboard, which is the most-loaded page in the app,
and an organization with 50,000 documents should not load 50,000 rows to count
them.

The month boundary and the "what counts against the plan" rule are deliberately
shared with usage.py rather than reimplemented. If the dashboard said 94 and
billing said 96, neither number would be believed again.
"""
from datetime import datetime, timedelta

from extensions import db
from models import DuplicateMatch, Extraction
from plans import start_of_month
from usage import usage_for

# Validation verdicts that mean a person still needs to look.
NEEDS_ATTENTION = ("requires_review", "invalid")

# Window for the activity trend on the dashboard.
TREND_DAYS = 30


def _base(organization_id):
    """Live documents for an organization. Soft-deleted rows are excluded
    everywhere EXCEPT the plan counter, which deliberately still counts them -
    deleting history must not hand back quota."""
    return Extraction.query.filter(
        Extraction.organization_id == organization_id,
        Extraction.deleted_at.is_(None),
    )


def _count(query) -> int:
    return query.order_by(None).count()


def processing_stats(organization) -> dict:
    """Counts, success rate and timing for the organization's documents."""
    org_id = organization.id
    month_start = start_of_month()

    total = _count(_base(org_id))
    completed = _count(_base(org_id).filter(Extraction.status == "completed"))
    failed = _count(_base(org_id).filter(Extraction.status == "failed"))
    processing = _count(_base(org_id).filter(Extraction.status == "processing"))

    # "Awaiting review" means a completed document whose validation flagged
    # something and which nobody has opened since. A document someone has
    # already looked at is not still waiting, whatever its verdict.
    awaiting_review = _count(
        _base(org_id).filter(
            Extraction.status == "completed",
            Extraction.validation_status.in_(NEEDS_ATTENTION),
            Extraction.reviewed_at.is_(None),
        )
    )

    unresolved_duplicates = (
        db.session.query(db.func.count(db.distinct(DuplicateMatch.extraction_id)))
        .filter(
            DuplicateMatch.organization_id == org_id,
            DuplicateMatch.status == "pending",
        )
        .scalar()
    ) or 0

    # Averaged over completed runs only: a failure that timed out after 300s
    # would otherwise dominate the average and make extraction look slow.
    average_ms = (
        db.session.query(db.func.avg(Extraction.processing_ms))
        .filter(
            Extraction.organization_id == org_id,
            Extraction.deleted_at.is_(None),
            Extraction.status == "completed",
            Extraction.processing_ms.isnot(None),
        )
        .scalar()
    )

    attempted = completed + failed
    return {
        "total": total,
        "completed": completed,
        "failed": failed,
        "processing": processing,
        "awaitingReview": awaiting_review,
        "unresolvedDuplicates": unresolved_duplicates,
        # Of the runs that finished one way or the other. Documents still in
        # flight are excluded so the rate does not dip while one is running.
        "successRate": round(completed / attempted, 4) if attempted else None,
        "averageProcessingMs": int(average_ms) if average_ms is not None else None,
        "thisMonth": {
            "uploaded": _count(_base(org_id).filter(Extraction.created_at >= month_start)),
            "completed": _count(
                _base(org_id).filter(
                    Extraction.created_at >= month_start,
                    Extraction.status == "completed",
                )
            ),
            "failed": _count(
                _base(org_id).filter(
                    Extraction.created_at >= month_start,
                    Extraction.status == "failed",
                )
            ),
        },
    }


def validation_breakdown(organization) -> dict:
    """How many documents sit at each validation verdict."""
    rows = (
        db.session.query(Extraction.validation_status, db.func.count(Extraction.id))
        .filter(
            Extraction.organization_id == organization.id,
            Extraction.deleted_at.is_(None),
            Extraction.status == "completed",
            Extraction.validation_status.isnot(None),
        )
        .group_by(Extraction.validation_status)
        .all()
    )
    counts = dict(rows)
    # Always return every key so the UI does not have to guard each one.
    return {
        key: counts.get(key, 0)
        for key in ("valid", "valid_with_warnings", "requires_review", "invalid")
    }


def activity_trend(organization, days=TREND_DAYS) -> list:
    """Documents processed per day, oldest first, with empty days filled in.

    Gaps are filled because a chart that silently skips quiet days implies
    activity that did not happen.
    """
    since = datetime.utcnow().date() - timedelta(days=days - 1)
    rows = (
        db.session.query(
            db.func.date(Extraction.created_at), db.func.count(Extraction.id)
        )
        .filter(
            Extraction.organization_id == organization.id,
            Extraction.deleted_at.is_(None),
            Extraction.created_at >= datetime.combine(since, datetime.min.time()),
        )
        .group_by(db.func.date(Extraction.created_at))
        .all()
    )
    # SQLite returns a string from date(); Postgres returns a date object.
    counts = {}
    for day, count in rows:
        key = day if isinstance(day, str) else day.isoformat()
        counts[key] = count

    return [
        {
            "date": (since + timedelta(days=offset)).isoformat(),
            "count": counts.get((since + timedelta(days=offset)).isoformat(), 0),
        }
        for offset in range(days)
    ]


def dashboard_stats(organization) -> dict:
    """Everything the usage dashboard shows, in one response.

    `usage` comes from usage.py unchanged, so the allowance on this page and
    the allowance billing enforces can never disagree.
    """
    return {
        "processing": processing_stats(organization),
        "validation": validation_breakdown(organization),
        "trend": activity_trend(organization),
        "usage": usage_for(organization),
    }
