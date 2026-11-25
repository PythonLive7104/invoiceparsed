"""Payment tracking: what has been paid against an invoice, and what has not.

**This module initiates no payments.** It records payments somebody has
already made through their bank. That boundary is deliberate and worth
defending: the moment software can move money out of a business it becomes the
most valuable thing in the building to compromise, and every control around it
would have to be an order of magnitude stronger than anything else here. The
product holds no payment credentials and has no code path that could.

Three rules.

1. **The position is recomputed, never incremented.** `recompute_payment_state`
   rewrites `amount_paid` and `payment_state` from the payment rows on every
   change. Incrementing would drift the first time a payment was voided or an
   amount corrected, and a silently wrong "paid to date" is the figure that
   gets an invoice paid twice. The same discipline as `recompute_invoiced` and
   `recompute_received`.

2. **Voided, never deleted.** A payment recorded in error is a thing somebody
   asserted, and the correction is part of the record.

3. **A dispute outranks arithmetic.** It is a human assertion rather than a
   derived figure, and an invoice somebody is arguing about must not sit
   quietly in "overdue" where a payment run will sweep it up.
"""
import logging
from datetime import date, datetime
from decimal import Decimal

from extensions import db
from models import Extraction, SupplierPayment
from money import money, to_decimal

logger = logging.getLogger(__name__)

UNPAID = "unpaid"
PARTIALLY_PAID = "partially_paid"
PAID = "paid"
OVERDUE = "overdue"
DISPUTED = "disputed"
STATES = (UNPAID, PARTIALLY_PAID, PAID, OVERDUE, DISPUTED)

# Open states, for "what still needs paying".
OPEN_STATES = (UNPAID, PARTIALLY_PAID, OVERDUE, DISPUTED)

ZERO = Decimal("0")
# A penny either way is settled. Suppliers round, banks round, and chasing a
# cent costs more than the cent.
SETTLED_TOLERANCE = Decimal("0.01")

MAX_PAYMENTS_PER_INVOICE = 200


class PaymentError(Exception):
    def __init__(self, message: str, code: str = "INVALID_PAYMENT"):
        super().__init__(message)
        self.message = message
        self.code = code


def _parse_date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip()[:10]).date()
    except ValueError:
        return None


# ─── The position ────────────────────────────────────────────────────────────
def paid_against(extraction: Extraction) -> Decimal:
    """Total of the live (non-void) payments against one invoice.

    Summed in SQL rather than by loading every row, because this runs whenever
    an invoice is read.
    """
    total = (
        db.session.query(
            db.func.sum(SupplierPayment.amount, type_=db.Numeric(18, 4))
        )
        .filter(
            SupplierPayment.extraction_id == extraction.id,
            SupplierPayment.organization_id == extraction.organization_id,
            SupplierPayment.voided_at.is_(None),
        )
        .scalar()
    )
    return to_decimal(total) or ZERO


def outstanding(extraction: Extraction) -> Decimal:
    """What is still owed. Never negative: an overpayment is a credit to chase,
    not a negative debt, and showing it as one would make a supplier statement
    total wrongly."""
    invoiced = to_decimal(extraction.total) or ZERO
    remaining = invoiced - (to_decimal(extraction.amount_paid) or ZERO)
    return remaining if remaining > 0 else ZERO


def payment_state(extraction: Extraction, *, today=None) -> str:
    """The state this invoice is in, from its figures and its due date.

    A pure function of the row, so it can be reasoned about and tested without
    a database. `recompute_payment_state` is what writes the answer down.
    """
    if extraction.disputed_at is not None:
        return DISPUTED

    invoiced = to_decimal(extraction.total) or ZERO
    paid = to_decimal(extraction.amount_paid) or ZERO

    if invoiced > 0 and paid >= invoiced - SETTLED_TOLERANCE:
        return PAID

    # Overdue outranks unpaid and partially paid, because the useful question
    # is "what is late", not "what is untouched".
    due = _parse_date(extraction.due_date)
    if due is not None and due < (today or date.today()):
        return OVERDUE

    if paid > 0:
        return PARTIALLY_PAID
    return UNPAID


def recompute_payment_state(extraction: Extraction, *, today=None) -> None:
    """Rewrite the cached payment position on one invoice. The single writer."""
    extraction.amount_paid = paid_against(extraction)
    extraction.payment_state = payment_state(extraction, today=today)


# ─── Recording ───────────────────────────────────────────────────────────────
def validate_payment(body: dict, extraction: Extraction) -> tuple[dict, dict]:
    """Check a payment before it is recorded. Returns (fields, errors)."""
    errors: dict[str, str] = {}
    fields: dict = {}

    amount = money(body.get("amount"))
    if amount is None:
        errors["amount"] = "Enter an amount."
    elif amount <= 0:
        # A zero payment records nothing; a negative one is a refund, which is
        # a credit note against the invoice rather than a payment of it.
        errors["amount"] = "A payment must be more than zero."
    else:
        fields["amount"] = amount

    method = (body.get("method") or SupplierPayment.BANK_TRANSFER).strip()
    if method not in SupplierPayment.METHODS:
        errors["method"] = "Choose a payment method."
    fields["method"] = method

    paid_on = (body.get("paidOn") or "").strip() or None
    if paid_on and _parse_date(paid_on) is None:
        errors["paidOn"] = "Use a date like 2026-11-24."
    elif paid_on and _parse_date(paid_on) > date.today():
        # Recording a payment that has not happened yet turns this from a
        # record into a plan, and plans do not belong in a ledger.
        errors["paidOn"] = "A payment cannot be dated in the future."
    fields["paid_on"] = paid_on or date.today().isoformat()

    for key, column, limit in (
        ("reference", "reference", 200),
        ("notes", "notes", 500),
    ):
        value = (body.get(key) or "").strip() or None
        if value and len(value) > limit:
            errors[key] = f"Keep this under {limit} characters."
        fields[column] = value

    fields["currency"] = (
        (body.get("currency") or "").strip().upper() or extraction.currency
    )
    return fields, errors


def check_can_record(extraction: Extraction) -> None:
    """Raise unless a payment may be recorded against this invoice."""
    if extraction.deleted_at is not None:
        raise PaymentError("That invoice has been deleted.", "INVOICE_DELETED")
    if extraction.doc_type != "invoice":
        raise PaymentError(
            "Payments are recorded against invoices.", "NOT_AN_INVOICE",
        )
    count = (
        db.session.query(db.func.count(SupplierPayment.id))
        .filter(SupplierPayment.extraction_id == extraction.id)
        .scalar()
    ) or 0
    if count >= MAX_PAYMENTS_PER_INVOICE:
        raise PaymentError(
            f"This invoice already has {MAX_PAYMENTS_PER_INVOICE} payments "
            "recorded against it.",
            "TOO_MANY_PAYMENTS",
        )


def would_overpay(extraction: Extraction, amount) -> Decimal:
    """How much this payment would exceed what is outstanding, or zero.

    Reported rather than refused. Overpaying happens — a duplicate bank run, a
    deliberate payment on account — and refusing to record something that has
    already left the bank account would make the ledger disagree with the bank,
    which is worse than a flagged overpayment.
    """
    over = (to_decimal(amount) or ZERO) - outstanding(extraction)
    return over if over > SETTLED_TOLERANCE else ZERO


def dispute(extraction: Extraction, *, user_id: str, reason: str) -> None:
    if not (reason or "").strip():
        raise PaymentError("Say what is disputed.", "REASON_REQUIRED")
    extraction.disputed_at = datetime.utcnow()
    extraction.disputed_by_user_id = user_id
    extraction.dispute_reason = reason.strip()[:500]
    recompute_payment_state(extraction)


def settle_dispute(extraction: Extraction) -> None:
    """Withdraw a dispute. The invoice returns to whatever its figures say."""
    if extraction.disputed_at is None:
        raise PaymentError("This invoice is not disputed.", "NOT_DISPUTED")
    extraction.disputed_at = None
    extraction.disputed_by_user_id = None
    extraction.dispute_reason = None
    recompute_payment_state(extraction)


# ─── Aggregates ──────────────────────────────────────────────────────────────
def payables_summary(organization_id: str, *, today=None) -> dict:
    """What is owed, by state and per currency.

    Per currency, never summed across them: one total spanning NGN and USD is
    a meaningless number that looks authoritative, which is worse than showing
    nothing.
    """
    rows = (
        db.session.query(
            Extraction.payment_state,
            Extraction.currency,
            db.func.count(Extraction.id),
            db.func.sum(Extraction.total, type_=db.Numeric(18, 4)),
            db.func.sum(Extraction.amount_paid, type_=db.Numeric(18, 4)),
        )
        .filter(
            Extraction.organization_id == organization_id,
            Extraction.deleted_at.is_(None),
            Extraction.doc_type == "invoice",
            Extraction.status == "completed",
        )
        .group_by(Extraction.payment_state, Extraction.currency)
        .all()
    )

    by_state = {state: 0 for state in STATES}
    outstanding_by_currency: dict[str, Decimal] = {}
    for state, currency, count, invoiced, paid in rows:
        if state in by_state:
            by_state[state] += count
        if state in OPEN_STATES:
            owed = (to_decimal(invoiced) or ZERO) - (to_decimal(paid) or ZERO)
            if owed > 0:
                key = currency or "—"
                outstanding_by_currency[key] = (
                    outstanding_by_currency.get(key, ZERO) + owed
                )

    return {
        "byState": by_state,
        "outstandingByCurrency": [
            {"currency": currency, "amount": amount}
            for currency, amount in sorted(outstanding_by_currency.items())
        ],
    }


def refresh_overdue(organization_id: str, *, today=None) -> int:
    """Move invoices into (or out of) `overdue` as the calendar moves.

    Overdue is the one state that changes without anybody touching anything,
    so it cannot be maintained only on write. Called when the payables list is
    read, which is the moment the answer matters, rather than from a scheduled
    job this deployment does not have.
    """
    today = today or date.today()
    candidates = (
        Extraction.query.filter(
            Extraction.organization_id == organization_id,
            Extraction.deleted_at.is_(None),
            Extraction.doc_type == "invoice",
            Extraction.status == "completed",
            db.or_(
                Extraction.payment_state.in_((UNPAID, PARTIALLY_PAID, OVERDUE)),
                Extraction.payment_state.is_(None),
            ),
        )
        .limit(2000)
        .all()
    )
    changed = 0
    for row in candidates:
        current = row.payment_state
        fresh = payment_state(row, today=today)
        if fresh != current:
            row.payment_state = fresh
            changed += 1
    return changed
