"""Invoice validation.

The engine exists to catch what the extractor got wrong, so these tests are
mostly "the model returned something plausible but incorrect — is it caught?".
"""
from datetime import date

import pytest

from invoice_schema import normalize
from validation import (
    INVALID,
    REQUIRES_REVIEW,
    VALID,
    VALID_WITH_WARNINGS,
    validate_invoice,
)

TODAY = date(2026, 11, 22)


def _invoice(**overrides):
    """A clean, internally consistent invoice: 2 x 100 + 20 = 220, +10% tax."""
    base = {
        "vendor": {"name": "Acme Ltd", "email": "ar@acme.example",
                   "address": "1 Trade St", "tax_id": "TIN-1"},
        "customer": {"name": "Buyer Co"},
        "invoice_number": "INV-1",
        "invoice_date": "2026-11-01",
        "due_date": "2026-12-01",
        "currency": "USD",
        "line_items": [
            {"description": "Design", "quantity": 2, "unit_price": 100, "amount": 200},
            {"description": "Hosting", "quantity": 1, "unit_price": 20, "amount": 20},
        ],
        "subtotal": 220, "tax": 22, "tax_percentage": 10, "total": 242,
        "confidence": {},
    }
    base.update(overrides)
    return normalize(base)


def _codes(result):
    return {i["code"] for i in result["issues"]}


def _run(inv):
    return validate_invoice(inv, today=TODAY)


# ─── The happy path ──────────────────────────────────────────────────────────
def test_a_consistent_invoice_is_valid():
    result = _run(_invoice())
    assert result["status"] == VALID, result["issues"]
    assert result["issues"] == []


def test_validation_never_modifies_the_invoice():
    """Silently correcting a figure would destroy the evidence of what the
    document actually said."""
    inv = _invoice(total=999)
    before = dict(inv)
    _run(inv)
    assert inv == before


# ─── Required fields ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("field,code", [
    ("invoice_number", "missing_invoice_number"),
    ("invoice_date", "missing_invoice_date"),
    ("total", "missing_total"),
    ("currency", "missing_currency"),
])
def test_a_missing_required_field_is_invalid(field, code):
    result = _run(_invoice(**{field: None}))
    assert result["status"] == INVALID
    assert code in _codes(result)


def test_missing_supplier_name_is_invalid():
    result = _run(_invoice(vendor={"name": None}))
    assert result["status"] == INVALID
    assert "missing_vendor_name" in _codes(result)


def test_required_fields_are_configurable():
    """Organizations differ on what they insist upon."""
    inv = _invoice(due_date=None)
    assert _run(inv)["status"] == VALID
    strict = validate_invoice(inv, required_fields=("due_date",), today=TODAY)
    assert strict["status"] == INVALID
    assert "missing_due_date" in _codes(strict)


# ─── Arithmetic: the point of the engine ─────────────────────────────────────
def test_line_items_not_matching_the_subtotal():
    result = _run(_invoice(subtotal=260))
    assert result["status"] == REQUIRES_REVIEW
    assert "subtotal_mismatch" in _codes(result)
    message = next(i for i in result["issues"] if i["code"] == "subtotal_mismatch")["message"]
    # The numbers must be in the message; "subtotal mismatch" alone is useless.
    assert "220.00" in message and "260.00" in message


def test_a_line_whose_maths_does_not_work():
    inv = _invoice(line_items=[
        {"description": "Widget", "quantity": 3, "unit_price": 10, "amount": 25},
    ], subtotal=25, tax=0, tax_percentage=0, total=25)
    result = _run(inv)
    assert "line_total_mismatch" in _codes(result)
    message = next(i for i in result["issues"] if i["code"] == "line_total_mismatch")["message"]
    assert "Widget" in message and "30.00" in message and "25.00" in message


def test_totals_that_do_not_add_up():
    result = _run(_invoice(total=300))
    assert result["status"] == REQUIRES_REVIEW
    assert "total_mismatch" in _codes(result)


def test_tax_inconsistent_with_the_stated_rate():
    result = _run(_invoice(tax=50, total=270))
    assert "tax_mismatch" in _codes(result)


def test_balance_due_that_does_not_follow():
    result = _run(_invoice(amount_paid=100, balance_due=200))
    assert "balance_mismatch" in _codes(result)


def test_paying_more_than_the_invoice():
    result = _run(_invoice(amount_paid=500, balance_due=0))
    assert "overpaid" in _codes(result)


def test_small_rounding_differences_are_tolerated():
    """Per-line rounding on a long invoice must not cry wolf."""
    result = _run(_invoice(subtotal="220.01", total="242.01"))
    assert result["status"] == VALID, result["issues"]


def test_a_negative_total_is_fine_on_a_credit_note():
    credit = _invoice(invoice_type="credit_note", line_items=[
        {"description": "Refund", "quantity": 1, "unit_price": -100, "amount": -100},
    ], subtotal=-100, tax=0, tax_percentage=0, total=-100)
    assert "negative_total" not in _codes(_run(credit))

    charge = _invoice(line_items=[
        {"description": "Refund", "quantity": 1, "unit_price": -100, "amount": -100},
    ], subtotal=-100, tax=0, tax_percentage=0, total=-100)
    assert "negative_total" in _codes(_run(charge))


def test_arithmetic_is_skipped_rather_than_guessed_when_data_is_absent():
    """A missing subtotal is a missing-field problem, not a maths problem."""
    result = _run(_invoice(subtotal=None, tax=None, tax_percentage=None))
    assert "subtotal_mismatch" not in _codes(result)
    assert "total_mismatch" not in _codes(result)


# ─── Dates ───────────────────────────────────────────────────────────────────
def test_due_date_before_the_invoice_date():
    result = _run(_invoice(invoice_date="2026-11-10", due_date="2026-11-01"))
    assert result["status"] == REQUIRES_REVIEW
    assert "due_before_invoice" in _codes(result)


def test_a_future_invoice_date():
    result = _run(_invoice(invoice_date="2027-06-01", due_date="2027-07-01"))
    assert "future_invoice_date" in _codes(result)


def test_a_very_old_invoice_is_flagged_not_rejected():
    """Usually a misread year or a re-upload - worth a look, not a block."""
    result = _run(_invoice(invoice_date="2019-01-01", due_date="2019-02-01"))
    assert "stale_invoice" in _codes(result)
    assert result["status"] == VALID_WITH_WARNINGS


def test_an_unreadable_date():
    result = _run(_invoice(invoice_date="sometime in March"))
    assert "invoice_date_unparseable" in _codes(result)


# ─── Supplier and currency ───────────────────────────────────────────────────
def test_a_supplier_with_no_identifying_details():
    result = _run(_invoice(vendor={"name": "Acme Ltd"}))
    assert "supplier_unidentifiable" in _codes(result)


def test_a_malformed_supplier_email():
    result = _run(_invoice(vendor={"name": "Acme", "email": "not-an-email", "tax_id": "T1"}))
    assert "supplier_email_invalid" in _codes(result)


def test_a_currency_that_is_not_an_iso_code():
    result = _run(_invoice(currency="dollars"))
    assert "currency_not_iso" in _codes(result)


# ─── Confidence ──────────────────────────────────────────────────────────────
def test_low_extractor_confidence_routes_to_review():
    """The model's own uncertainty is the cheapest signal that a human should
    look; ignoring it means trusting a guess."""
    inv = _invoice()
    inv["confidence"] = {"total": 0.2, "invoice_number": 0.3, "vendor": 0.95}
    result = _run(inv)
    assert result["status"] == REQUIRES_REVIEW
    message = next(i for i in result["issues"] if i["code"] == "low_confidence")["message"]
    assert "total" in message and "invoice_number" in message
    assert "vendor" not in message


def test_high_confidence_raises_nothing():
    inv = _invoice()
    inv["confidence"] = {k: 0.99 for k in ("total", "invoice_number", "vendor")}
    assert _run(inv)["status"] == VALID


# ─── Status aggregation ──────────────────────────────────────────────────────
def test_the_worst_severity_decides_the_status():
    inv = _invoice(currency="dollars", total=None)  # a warning and an error
    result = _run(inv)
    assert result["status"] == INVALID
    assert result["counts"]["error"] >= 1
    assert result["counts"]["warning"] >= 1


def test_counts_and_issue_count_agree():
    result = _run(_invoice(subtotal=260, currency="dollars"))
    assert result["issueCount"] == len(result["issues"])
    assert sum(result["counts"].values()) == result["issueCount"]


def test_an_empty_document_does_not_crash():
    result = validate_invoice({}, today=TODAY)
    assert result["status"] == INVALID
    assert result["issueCount"] > 0


def test_every_issue_has_a_code_severity_and_message():
    result = _run(_invoice(subtotal=260, currency="dollars", total=None))
    for issue in result["issues"]:
        assert issue["code"] and issue["severity"] and issue["message"]
        assert issue["severity"] in ("error", "review", "warning")
