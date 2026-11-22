"""Usage and processing statistics.

The dashboard and the billing allowance must agree. If this page said 94 and
billing enforced 96, neither number would be trusted again - so the allowance
here comes from the same code billing uses, and these tests pin that.
"""
from datetime import datetime, timedelta

import pytest

from extensions import db
from models import DuplicateMatch, Extraction
from tests.conftest import auth_header, make_user


@pytest.fixture
def account(app):
    user = make_user(app, email="stats@example.com", plan="free")  # limit: 5
    return user, auth_header(app, user)


def _seed(app, user, **overrides):
    with app.app_context():
        row = Extraction(
            organization_id=user["organization_id"],
            user_id=user["id"],
            doc_type=overrides.pop("doc_type", "invoice"),
            file_name=overrides.pop("file_name", "inv.pdf"),
            file_type="application/pdf",
            file_size=10,
            data="{}",
            status=overrides.pop("status", "completed"),
        )
        for key, value in overrides.items():
            setattr(row, key, value)
        db.session.add(row)
        db.session.commit()
        return row.id


def _stats(client, headers):
    r = client.get("/api/usage/stats", headers=headers)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


# ─── Counts ──────────────────────────────────────────────────────────────────
def test_counts_by_processing_status(client, app, account):
    user, headers = account
    _seed(app, user, status="completed")
    _seed(app, user, status="completed")
    _seed(app, user, status="failed")
    _seed(app, user, status="processing")

    p = _stats(client, headers)["processing"]
    assert p["total"] == 4
    assert p["completed"] == 2
    assert p["failed"] == 1
    assert p["processing"] == 1


def test_success_rate_ignores_documents_still_running(client, app, account):
    """A rate that dips while an extraction is in flight would look like a
    reliability problem that is not happening."""
    user, headers = account
    for _ in range(3):
        _seed(app, user, status="completed")
    _seed(app, user, status="failed")
    _seed(app, user, status="processing")

    assert _stats(client, headers)["processing"]["successRate"] == 0.75


def test_success_rate_is_null_before_anything_has_run(client, app, account):
    """None, not 0 - zero would read as 'everything fails'."""
    _user, headers = account
    assert _stats(client, headers)["processing"]["successRate"] is None


def test_average_time_uses_completed_runs_only(client, app, account):
    """A failure that timed out after five minutes would otherwise dominate the
    average and make extraction look slow."""
    user, headers = account
    _seed(app, user, status="completed", processing_ms=1000)
    _seed(app, user, status="completed", processing_ms=3000)
    _seed(app, user, status="failed", processing_ms=300000)

    assert _stats(client, headers)["processing"]["averageProcessingMs"] == 2000


def test_deleted_documents_do_not_count(client, app, account):
    user, headers = account
    _seed(app, user)
    _seed(app, user, deleted_at=datetime.utcnow())
    assert _stats(client, headers)["processing"]["total"] == 1


# ─── Awaiting review ─────────────────────────────────────────────────────────
def test_awaiting_review_counts_flagged_and_unseen(client, app, account):
    user, headers = account
    _seed(app, user, validation_status="requires_review")
    _seed(app, user, validation_status="invalid")
    _seed(app, user, validation_status="valid")
    _seed(app, user, validation_status="valid_with_warnings")

    assert _stats(client, headers)["processing"]["awaitingReview"] == 2


def test_a_document_someone_has_reviewed_is_no_longer_waiting(client, app, account):
    """Whatever its verdict - it is not waiting if a person has looked at it."""
    user, headers = account
    _seed(app, user, validation_status="requires_review",
          reviewed_at=datetime.utcnow())
    assert _stats(client, headers)["processing"]["awaitingReview"] == 0


def test_a_failed_document_is_not_awaiting_review(client, app, account):
    """It needs re-running, not reviewing; counting it would conflate two very
    different actions."""
    user, headers = account
    _seed(app, user, status="failed", validation_status="invalid")
    assert _stats(client, headers)["processing"]["awaitingReview"] == 0


def test_unresolved_duplicates_are_counted_once_per_document(client, app, account):
    user, headers = account
    first = _seed(app, user, file_name="a.pdf")
    second = _seed(app, user, file_name="b.pdf")
    with app.app_context():
        for reason in ("exact_file", "same_number"):
            db.session.add(DuplicateMatch(
                organization_id=user["organization_id"],
                extraction_id=second, duplicate_of_id=first,
                reason=reason, score=1.0, status="pending",
            ))
        db.session.commit()
    # Two findings, but one document needing a decision.
    assert _stats(client, headers)["processing"]["unresolvedDuplicates"] == 1


def test_dismissed_duplicates_stop_counting(client, app, account):
    user, headers = account
    first = _seed(app, user, file_name="a.pdf")
    second = _seed(app, user, file_name="b.pdf")
    with app.app_context():
        db.session.add(DuplicateMatch(
            organization_id=user["organization_id"],
            extraction_id=second, duplicate_of_id=first,
            reason="exact_file", score=1.0, status="dismissed",
        ))
        db.session.commit()
    assert _stats(client, headers)["processing"]["unresolvedDuplicates"] == 0


# ─── Validation breakdown ────────────────────────────────────────────────────
def test_validation_breakdown_counts_each_verdict(client, app, account):
    user, headers = account
    _seed(app, user, validation_status="valid")
    _seed(app, user, validation_status="requires_review")
    breakdown = _stats(client, headers)["validation"]
    assert set(breakdown) == {
        "valid", "valid_with_warnings", "requires_review", "invalid",
    }
    assert breakdown["valid"] == 1
    assert breakdown["requires_review"] == 1
    assert breakdown["invalid"] == 0


# ─── Allowance: must agree with billing ──────────────────────────────────────
def test_the_allowance_matches_what_billing_reports(client, app, account):
    """One number, one source. Two that disagree make both useless."""
    user, headers = account
    for _ in range(3):
        _seed(app, user, status="completed")

    from_stats = _stats(client, headers)["usage"]
    from_billing = client.get("/api/usage", headers=headers).get_json()["usage"]
    assert from_stats == from_billing


def test_failed_documents_do_not_consume_the_allowance(client, app, account):
    """Charging someone for a run that produced nothing is indefensible."""
    user, headers = account
    _seed(app, user, status="completed")
    _seed(app, user, status="failed")
    _seed(app, user, status="failed")

    usage = _stats(client, headers)["usage"]
    assert usage["used"] == 1
    assert usage["remaining"] == 4  # free plan allows 5


def test_deleting_history_does_not_hand_back_allowance(client, app, account):
    """Otherwise the monthly limit resets on demand."""
    user, headers = account
    _seed(app, user, status="completed")
    _seed(app, user, status="completed", deleted_at=datetime.utcnow())

    body = _stats(client, headers)
    assert body["usage"]["used"] == 2
    # ...while the processing view shows only what still exists.
    assert body["processing"]["total"] == 1


# ─── Trend ───────────────────────────────────────────────────────────────────
def test_the_trend_fills_quiet_days(client, app, account):
    """A chart that skips empty days implies activity that did not happen."""
    user, headers = account
    _seed(app, user)
    trend = _stats(client, headers)["trend"]
    assert len(trend) == 30
    assert trend[0]["date"] < trend[-1]["date"]      # oldest first
    assert sum(point["count"] for point in trend) == 1
    assert all("count" in point for point in trend)


def test_the_trend_excludes_older_documents(client, app, account):
    user, headers = account
    old_id = _seed(app, user)
    with app.app_context():
        row = Extraction.query.filter_by(id=old_id).first()
        row.created_at = datetime.utcnow() - timedelta(days=90)
        db.session.commit()
    assert sum(p["count"] for p in _stats(client, headers)["trend"]) == 0


# ─── Isolation ───────────────────────────────────────────────────────────────
def test_stats_never_include_another_organization(client, app):
    alice = make_user(app, email="as@example.com", plan="pro")
    bob = make_user(app, email="bs@example.com", plan="pro")
    for _ in range(5):
        _seed(app, alice)
    _seed(app, bob)

    assert _stats(client, auth_header(app, bob))["processing"]["total"] == 1


def test_an_empty_organization_returns_zeroes_not_errors(client, app, account):
    _user, headers = account
    body = _stats(client, headers)
    assert body["processing"]["total"] == 0
    assert body["processing"]["averageProcessingMs"] is None
    assert body["usage"]["used"] == 0
    assert len(body["trend"]) == 30
