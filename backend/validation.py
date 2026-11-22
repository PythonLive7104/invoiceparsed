"""Invoice validation.

Checks an extracted invoice for missing fields, arithmetic that does not add
up, impossible dates and unusable supplier details, and returns a status plus
a specific explanation for every problem found.

Three principles:

1. **Validation never changes the data.** It reports. Silently "correcting" a
   figure on a financial document would destroy the evidence of what the
   document actually said, which is the one thing a finance team needs.
2. **The arithmetic is ours, not the model's.** Every total is recomputed in
   Decimal and compared to what was extracted. This is what catches an
   otherwise confident-looking extraction that misread a digit.
3. **A warning names the numbers.** "Line items total 24,500.00 but subtotal
   says 26,000.00 (difference 1,500.00)" is actionable; "subtotal mismatch" is
   not.

Severity decides the status, so adding a check never requires touching the
status logic:
  error   -> INVALID        (cannot be trusted)
  review  -> REQUIRES_REVIEW (probably wrong, a human should look)
  warning -> VALID_WITH_WARNINGS (worth knowing, not blocking)
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from money import money, money_sum, to_decimal

# ─── Status, worst first ─────────────────────────────────────────────────────
INVALID = "invalid"
REQUIRES_REVIEW = "requires_review"
VALID_WITH_WARNINGS = "valid_with_warnings"
VALID = "valid"

ERROR = "error"
REVIEW = "review"
WARNING = "warning"

_SEVERITY_STATUS = {ERROR: INVALID, REVIEW: REQUIRES_REVIEW, WARNING: VALID_WITH_WARNINGS}
_STATUS_RANK = {VALID: 0, VALID_WITH_WARNINGS: 1, REQUIRES_REVIEW: 2, INVALID: 3}

# Fields an invoice is unusable without. Organization-configurable later
# (P1.2 asks for it); this is the default set.
DEFAULT_REQUIRED_FIELDS = ("invoice_number", "vendor_name", "invoice_date", "total", "currency")

# How far totals may drift before it is reported. Covers ordinary per-line
# rounding on a long invoice without hiding a real transposition.
TOLERANCE = Decimal("0.02")

# Confidence at or below this routes the document to human review.
LOW_CONFIDENCE = 0.55

# An invoice older than this is probably a re-upload or a mis-read year.
STALE_AFTER = timedelta(days=365 * 2)


def _issue(code, severity, message, field=None):
    return {"code": code, "severity": severity, "message": message, "field": field}


def _fmt(value) -> str:
    """Format an amount for a human-readable message."""
    parsed = to_decimal(value)
    return "—" if parsed is None else f"{parsed:,.2f}"


def _parse_date(value):
    """Parse an ISO date. None when absent or unparseable."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip()[:10]).date()
    except ValueError:
        return None


# ─── Individual checks ───────────────────────────────────────────────────────
def _check_required(inv, required) -> list:
    present = {
        "invoice_number": inv.get("invoice_number"),
        "vendor_name": (inv.get("vendor") or {}).get("name"),
        "customer_name": (inv.get("customer") or {}).get("name"),
        "invoice_date": inv.get("invoice_date"),
        "due_date": inv.get("due_date"),
        "total": inv.get("total"),
        "currency": inv.get("currency"),
    }
    labels = {
        "invoice_number": "Invoice number", "vendor_name": "Supplier name",
        "customer_name": "Customer name", "invoice_date": "Invoice date",
        "due_date": "Due date", "total": "Total amount", "currency": "Currency",
    }
    issues = []
    for field in required:
        if present.get(field) in (None, ""):
            issues.append(_issue(
                f"missing_{field}", ERROR,
                f"{labels.get(field, field)} is missing.", field,
            ))
    return issues


def _check_arithmetic(inv) -> list:
    """Recompute the totals and compare them with what was extracted."""
    issues = []
    items = inv.get("line_items") or []

    # Line items -> subtotal.
    subtotal = inv.get("subtotal")
    if items and subtotal is not None:
        lines_total = money_sum(item.get("amount") for item in items)
        stated = money(subtotal)
        if stated is not None and abs(lines_total - stated) > TOLERANCE:
            issues.append(_issue(
                "subtotal_mismatch", REVIEW,
                f"Line items add up to {_fmt(lines_total)} but the subtotal says "
                f"{_fmt(stated)} (difference {_fmt(abs(lines_total - stated))}).",
                "subtotal",
            ))

    # Each line: quantity x unit price, less discount, should equal the amount.
    for index, item in enumerate(items):
        quantity = to_decimal(item.get("quantity"))
        unit_price = to_decimal(item.get("unit_price"))
        amount = money(item.get("amount"))
        if quantity is None or unit_price is None or amount is None:
            continue
        expected = money((quantity * unit_price) - (money(item.get("discount")) or 0))
        if expected is not None and abs(expected - amount) > TOLERANCE:
            label = item.get("description") or f"line {index + 1}"
            issues.append(_issue(
                "line_total_mismatch", WARNING,
                f"{label}: {_fmt(quantity)} x {_fmt(unit_price)} is "
                f"{_fmt(expected)}, but the line says {_fmt(amount)}.",
                f"line_items.{index}.amount",
            ))

    # subtotal - discount + tax + shipping + other = total.
    total = money(inv.get("total"))
    stated_subtotal = money(inv.get("subtotal"))
    if total is not None and stated_subtotal is not None:
        computed = stated_subtotal
        computed -= money(inv.get("discount")) or Decimal(0)
        computed += money(inv.get("tax")) or Decimal(0)
        computed += money(inv.get("shipping")) or Decimal(0)
        computed += money(inv.get("other_charges")) or Decimal(0)
        if abs(computed - total) > TOLERANCE:
            issues.append(_issue(
                "total_mismatch", REVIEW,
                f"Subtotal, tax and charges come to {_fmt(computed)} but the "
                f"total says {_fmt(total)} (difference {_fmt(abs(computed - total))}).",
                "total",
            ))

    # Stated tax vs the stated rate.
    tax = money(inv.get("tax"))
    rate = to_decimal(inv.get("tax_percentage"))
    if tax is not None and rate is not None and stated_subtotal is not None and rate > 0:
        expected_tax = money(stated_subtotal * rate / 100)
        if expected_tax is not None and abs(expected_tax - tax) > TOLERANCE:
            issues.append(_issue(
                "tax_mismatch", WARNING,
                f"{_fmt(rate)}% of {_fmt(stated_subtotal)} is {_fmt(expected_tax)}, "
                f"but the tax shown is {_fmt(tax)}.",
                "tax",
            ))

    # total - paid = balance due.
    paid = money(inv.get("amount_paid"))
    balance = money(inv.get("balance_due"))
    if total is not None and paid is not None and balance is not None:
        expected_balance = money(total - paid)
        if expected_balance is not None and abs(expected_balance - balance) > TOLERANCE:
            issues.append(_issue(
                "balance_mismatch", REVIEW,
                f"Total {_fmt(total)} less {_fmt(paid)} paid is "
                f"{_fmt(expected_balance)}, but the balance due says {_fmt(balance)}.",
                "balance_due",
            ))

    if total is not None and paid is not None and paid > total + TOLERANCE:
        issues.append(_issue(
            "overpaid", REVIEW,
            f"Amount paid ({_fmt(paid)}) is more than the invoice total "
            f"({_fmt(total)}).",
            "amount_paid",
        ))

    # A negative total on something that is not a credit note.
    if total is not None and total < 0 and inv.get("invoice_type") != "credit_note":
        issues.append(_issue(
            "negative_total", REVIEW,
            f"The total is negative ({_fmt(total)}) but this is not marked as a "
            f"credit note.",
            "total",
        ))
    return issues


def _check_dates(inv, today=None) -> list:
    today = today or date.today()
    issues = []
    raw_invoice_date = inv.get("invoice_date")
    raw_due_date = inv.get("due_date")

    invoice_date = _parse_date(raw_invoice_date)
    due_date = _parse_date(raw_due_date)

    if raw_invoice_date and invoice_date is None:
        issues.append(_issue(
            "invoice_date_unparseable", REVIEW,
            f"The invoice date '{raw_invoice_date}' is not a date we can read.",
            "invoice_date",
        ))
    if raw_due_date and due_date is None:
        issues.append(_issue(
            "due_date_unparseable", WARNING,
            f"The due date '{raw_due_date}' is not a date we can read.",
            "due_date",
        ))

    if invoice_date and due_date and due_date < invoice_date:
        issues.append(_issue(
            "due_before_invoice", REVIEW,
            f"The due date ({due_date}) is before the invoice date "
            f"({invoice_date}).",
            "due_date",
        ))
    if invoice_date and invoice_date > today:
        issues.append(_issue(
            "future_invoice_date", REVIEW,
            f"The invoice is dated {invoice_date}, which is in the future.",
            "invoice_date",
        ))
    if invoice_date and (today - invoice_date) > STALE_AFTER:
        issues.append(_issue(
            "stale_invoice", WARNING,
            f"The invoice is dated {invoice_date}, over two years ago. Check the "
            f"year was read correctly.",
            "invoice_date",
        ))
    return issues


def _check_supplier(inv) -> list:
    vendor = inv.get("vendor") or {}
    issues = []
    if not vendor.get("name"):
        return issues  # already reported as a missing required field

    identifying = any(vendor.get(k) for k in ("address", "email", "phone", "tax_id"))
    if not identifying:
        issues.append(_issue(
            "supplier_unidentifiable", WARNING,
            "No address, email, phone or tax ID for the supplier, so this "
            "invoice cannot be matched to a supplier record with confidence.",
            "vendor",
        ))

    email = vendor.get("email")
    if email and ("@" not in email or "." not in email.split("@")[-1]):
        issues.append(_issue(
            "supplier_email_invalid", WARNING,
            f"The supplier email '{email}' does not look like an address.",
            "vendor.email",
        ))
    return issues


def _check_currency(inv) -> list:
    currency = inv.get("currency")
    if currency and not (len(currency) == 3 and currency.isalpha()):
        return [_issue(
            "currency_not_iso", WARNING,
            f"'{currency}' is not a three-letter ISO 4217 currency code, so "
            f"amounts may be reported against the wrong currency.",
            "currency",
        )]
    return []


def _check_confidence(inv, threshold=LOW_CONFIDENCE) -> list:
    """Route a document to review when the extractor itself was unsure.

    The model's own uncertainty is the cheapest signal available that a figure
    needs a human; ignoring it means trusting a guess.
    """
    confidence = inv.get("confidence") or {}
    weak = sorted(
        field for field, score in confidence.items()
        if isinstance(score, int | float) and score <= threshold
    )
    if not weak:
        return []
    shown = ", ".join(weak[:5]) + (f" and {len(weak) - 5} more" if len(weak) > 5 else "")
    return [_issue(
        "low_confidence", REVIEW,
        f"The extractor was unsure about: {shown}. Check these against the "
        f"original document.",
        None,
    )]


# ─── Entry point ─────────────────────────────────────────────────────────────
def validate_invoice(inv: dict, *, required_fields=None, today=None) -> dict:
    """Validate a normalized invoice. Returns a status plus the issues found.

    `inv` is not modified.
    """
    inv = inv if isinstance(inv, dict) else {}
    required = tuple(required_fields or DEFAULT_REQUIRED_FIELDS)

    issues = [
        *_check_required(inv, required),
        *_check_arithmetic(inv),
        *_check_dates(inv, today=today),
        *_check_supplier(inv),
        *_check_currency(inv),
        *_check_confidence(inv),
    ]

    status = VALID
    for issue in issues:
        candidate = _SEVERITY_STATUS.get(issue["severity"], VALID_WITH_WARNINGS)
        if _STATUS_RANK[candidate] > _STATUS_RANK[status]:
            status = candidate

    counts = {ERROR: 0, REVIEW: 0, WARNING: 0}
    for issue in issues:
        if issue["severity"] in counts:
            counts[issue["severity"]] += 1

    return {
        "status": status,
        "issues": issues,
        "counts": counts,
        # Convenience for list views, which only need "is anything wrong".
        "issueCount": len(issues),
    }
