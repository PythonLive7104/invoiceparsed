"""Processing history: filters, search, sorting, pagination and export.

The list used to return a flat 300 rows with no filtering, which silently hid
everything older once an organization had processed a few hundred documents.
"""
import csv
import io
from datetime import datetime, timedelta

import pytest

from extensions import db
from models import Extraction
from tests.conftest import auth_header, make_user


@pytest.fixture
def account(app):
    user = make_user(app, email="hist@example.com", plan="pro")
    return user, auth_header(app, user)


def _seed(app, user, **overrides):
    """Insert a completed extraction directly; the history list only reads
    denormalized columns, so no extraction run is needed."""
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


def _list(client, headers, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
    r = client.get(f"/api/extractions?{query}", headers=headers)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


# ─── Pagination ──────────────────────────────────────────────────────────────
def test_results_are_paginated(client, app, account):
    user, headers = account
    for i in range(12):
        _seed(app, user, file_name=f"doc-{i:02d}.pdf")

    first = _list(client, headers, perPage=5)
    assert len(first["extractions"]) == 5
    assert first["total"] == 12
    assert first["pages"] == 3
    assert first["page"] == 1

    last = _list(client, headers, perPage=5, page=3)
    assert len(last["extractions"]) == 2


def test_pages_do_not_overlap(client, app, account):
    user, headers = account
    for i in range(10):
        _seed(app, user, file_name=f"doc-{i:02d}.pdf")

    page1 = {r["id"] for r in _list(client, headers, perPage=4, page=1)["extractions"]}
    page2 = {r["id"] for r in _list(client, headers, perPage=4, page=2)["extractions"]}
    assert page1 and page2 and not (page1 & page2)


def test_page_size_is_capped(client, app, account):
    """An unbounded perPage is a trivial way to make the server do too much."""
    user, headers = account
    for i in range(5):
        _seed(app, user, file_name=f"d{i}.pdf")
    body = _list(client, headers, perPage=100000)
    assert body["perPage"] <= 100


@pytest.mark.parametrize("page,per_page", [("abc", "xyz"), ("-5", "0")])
def test_nonsense_paging_values_fall_back_to_defaults(client, app, account, page, per_page):
    user, headers = account
    _seed(app, user)
    body = _list(client, headers, page=page, perPage=per_page)
    assert body["page"] >= 1 and body["perPage"] >= 1


# ─── Search ──────────────────────────────────────────────────────────────────
def test_search_matches_filename_supplier_or_invoice_number(client, app, account):
    user, headers = account
    _seed(app, user, file_name="acme-october.pdf", vendor_name="Acme Ltd",
          invoice_number="INV-900")
    _seed(app, user, file_name="other.pdf", vendor_name="Zenith", invoice_number="ZZ-1")

    for term in ("acme-october", "Acme", "INV-900"):
        found = _list(client, headers, q=term)["extractions"]
        assert len(found) == 1, term
        assert found[0]["vendorName"] == "Acme Ltd"


def test_search_is_case_insensitive(client, app, account):
    user, headers = account
    _seed(app, user, vendor_name="Acme Supplies")
    assert len(_list(client, headers, q="ACME")["extractions"]) == 1


def test_search_with_no_matches_returns_an_empty_page(client, app, account):
    user, headers = account
    _seed(app, user, vendor_name="Acme")
    body = _list(client, headers, q="nothing-like-this")
    assert body["extractions"] == []
    assert body["total"] == 0


# ─── Filters ─────────────────────────────────────────────────────────────────
def test_filter_by_processing_status(client, app, account):
    user, headers = account
    _seed(app, user, status="completed")
    _seed(app, user, status="failed", error_message="model timed out")
    assert len(_list(client, headers, status="failed")["extractions"]) == 1
    assert len(_list(client, headers, status="completed")["extractions"]) == 1


def test_filter_by_validation_status(client, app, account):
    """The point of denormalizing the verdict: 'show me everything that needs a
    human' in one query."""
    user, headers = account
    _seed(app, user, validation_status="valid")
    _seed(app, user, validation_status="requires_review", validation_issue_count=3)
    _seed(app, user, validation_status="requires_review", validation_issue_count=1)

    found = _list(client, headers, validationStatus="requires_review")["extractions"]
    assert len(found) == 2
    assert all(r["validationStatus"] == "requires_review" for r in found)


def test_filter_by_supplier_and_currency(client, app, account):
    user, headers = account
    _seed(app, user, vendor_name="Acme Ltd", currency="USD")
    _seed(app, user, vendor_name="Acme Ltd", currency="NGN")
    _seed(app, user, vendor_name="Zenith", currency="USD")

    assert len(_list(client, headers, vendor="Acme")["extractions"]) == 2
    assert len(_list(client, headers, currency="NGN")["extractions"]) == 1
    assert len(_list(client, headers, vendor="Acme", currency="USD")["extractions"]) == 1


def test_filter_by_amount_range(client, app, account):
    user, headers = account
    for amount in ("50.00", "500.00", "5000.00"):
        _seed(app, user, total=amount, file_name=f"{amount}.pdf")

    assert len(_list(client, headers, amountMin=100)["extractions"]) == 2
    assert len(_list(client, headers, amountMax=100)["extractions"]) == 1
    assert len(_list(client, headers, amountMin=100, amountMax=1000)["extractions"]) == 1


def test_filter_by_date_range_includes_the_whole_end_day(client, app, account):
    """A user picking 'to: 15 March' means the end of the 15th, not midnight at
    its start - otherwise that day's documents vanish."""
    user, headers = account
    with app.app_context():
        pass
    old_id = _seed(app, user, file_name="old.pdf")
    new_id = _seed(app, user, file_name="new.pdf")
    with app.app_context():
        old = Extraction.query.filter_by(id=old_id).first()
        old.created_at = datetime(2026, 3, 1, 9, 0)
        new = Extraction.query.filter_by(id=new_id).first()
        new.created_at = datetime(2026, 3, 15, 23, 30)
        db.session.commit()

    both = _list(client, headers, dateFrom="2026-03-01", dateTo="2026-03-15")
    assert {r["fileName"] for r in both["extractions"]} == {"old.pdf", "new.pdf"}

    only_old = _list(client, headers, dateTo="2026-03-02")
    assert {r["fileName"] for r in only_old["extractions"]} == {"old.pdf"}


def test_filter_by_reviewed_state(client, app, account):
    user, headers = account
    _seed(app, user, file_name="seen.pdf", reviewed_at=datetime.utcnow())
    _seed(app, user, file_name="unseen.pdf")

    assert len(_list(client, headers, reviewed="true")["extractions"]) == 1
    unreviewed = _list(client, headers, reviewed="false")["extractions"]
    assert [r["fileName"] for r in unreviewed] == ["unseen.pdf"]


def test_filters_combine(client, app, account):
    user, headers = account
    _seed(app, user, vendor_name="Acme", currency="USD", total="100.00",
          validation_status="requires_review")
    _seed(app, user, vendor_name="Acme", currency="USD", total="9000.00",
          validation_status="valid")

    found = _list(
        client, headers, vendor="Acme", currency="USD",
        validationStatus="requires_review", amountMax=1000,
    )["extractions"]
    assert len(found) == 1


def test_a_blank_filter_is_ignored(client, app, account):
    """The client sends the whole filter object; blanks must not exclude rows."""
    user, headers = account
    _seed(app, user)
    body = _list(client, headers, q="", vendor="", currency="", status="")
    assert body["total"] == 1


# ─── Sorting ─────────────────────────────────────────────────────────────────
def test_sort_by_total(client, app, account):
    user, headers = account
    for amount in ("300.00", "100.00", "200.00"):
        _seed(app, user, total=amount, file_name=f"{amount}.pdf")

    ascending = _list(client, headers, sort="total", order="asc")["extractions"]
    assert [r["total"] for r in ascending] == ["100.00", "200.00", "300.00"]
    descending = _list(client, headers, sort="total", order="desc")["extractions"]
    assert [r["total"] for r in descending] == ["300.00", "200.00", "100.00"]


def test_an_unknown_sort_key_falls_back_instead_of_erroring(client, app, account):
    """The sort key comes from the query string and feeds ORDER BY, so it is an
    allow-list; anything else quietly uses the default."""
    user, headers = account
    _seed(app, user)
    body = _list(client, headers, sort="total; DROP TABLE users")
    assert body["total"] == 1


# ─── Row content ─────────────────────────────────────────────────────────────
def test_a_row_carries_enough_to_triage_without_opening_it(client, app, account):
    user, headers = account
    _seed(app, user, vendor_name="Acme", total="42.00", currency="USD",
          validation_status="requires_review", validation_issue_count=2,
          extracted_field_count=14, processing_ms=3200)

    row = _list(client, headers)["extractions"][0]
    assert row["validationStatus"] == "requires_review"
    assert row["issueCount"] == 2
    assert row["fieldCount"] == 14
    assert row["processingMs"] == 3200
    assert row["total"] == "42.00"          # exact decimal string
    assert row["uploadedBy"]                 # who uploaded it
    assert row["reviewed"] is False


def test_a_failed_row_explains_itself(client, app, account):
    user, headers = account
    _seed(app, user, status="failed", error_message="The model returned invalid JSON.")
    row = _list(client, headers, status="failed")["extractions"][0]
    assert row["errorMessage"] == "The model returned invalid JSON."


# ─── Isolation ───────────────────────────────────────────────────────────────
def test_history_never_shows_another_organization(client, app):
    alice = make_user(app, email="ah@example.com", plan="pro")
    bob = make_user(app, email="bh@example.com", plan="pro")
    _seed(app, alice, file_name="alice.pdf")
    _seed(app, bob, file_name="bob.pdf")

    rows = _list(client, auth_header(app, bob))["extractions"]
    assert [r["fileName"] for r in rows] == ["bob.pdf"]


def test_deleted_documents_are_excluded(client, app, account):
    user, headers = account
    _seed(app, user, file_name="kept.pdf")
    _seed(app, user, file_name="gone.pdf", deleted_at=datetime.utcnow())
    rows = _list(client, headers)["extractions"]
    assert [r["fileName"] for r in rows] == ["kept.pdf"]


# ─── Export ──────────────────────────────────────────────────────────────────
def test_export_respects_the_current_filters(client, app, account):
    """What you see is what you export; an export that ignores the filters is a
    different report from the one on screen."""
    user, headers = account
    _seed(app, user, vendor_name="Acme", file_name="a.pdf")
    _seed(app, user, vendor_name="Zenith", file_name="z.pdf")

    r = client.get("/api/extractions/export?vendor=Acme", headers=headers)
    assert r.status_code == 200
    assert "text/csv" in r.headers["Content-Type"]
    rows = list(csv.reader(io.StringIO(r.get_data(as_text=True))))
    assert len(rows) == 2  # header + one match
    assert "Acme" in rows[1]


def test_export_includes_the_processing_record(client, app, account):
    user, headers = account
    _seed(app, user, vendor_name="Acme", validation_status="requires_review",
          validation_issue_count=3, processing_ms=1500, extracted_field_count=11)
    rows = list(csv.reader(io.StringIO(
        client.get("/api/extractions/export", headers=headers).get_data(as_text=True)
    )))
    header, row = rows[0], rows[1]
    cells = dict(zip(header, row, strict=True))
    assert cells["Validation"] == "requires_review"
    assert cells["Issues"] == "3"
    assert cells["Processing ms"] == "1500"
    assert cells["Fields"] == "11"
