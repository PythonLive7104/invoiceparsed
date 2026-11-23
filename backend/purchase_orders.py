"""Purchase-order arithmetic, numbering and lifecycle rules.

Kept out of the route layer so the rules are testable without HTTP and so
P2.3/P2.4 (invoice matching, three-way matching) can call the same arithmetic
rather than reimplementing it slightly differently — which is precisely how two
parts of a finance system end up disagreeing about a total.

Three rules are load-bearing:

1. **Totals are derived, never accepted from a client.** `recompute_totals`
   runs on every write. A stored total that disagrees with its own lines would
   make matching nonsense and is where both bugs and fraud hide.
2. **Each line is rounded before the lines are summed.** Suppliers print
   per-line amounts to 2dp and total those, so rounding only at the end can
   differ by a cent and raise a false mismatch against a perfectly good
   invoice.
3. **Status changes go through `transition`.** The allowed moves live in
   `PurchaseOrder.TRANSITIONS`; nothing else is permitted, so a PO can never
   reach a state the rest of the system has no handling for.
"""
import logging
import re
from datetime import datetime
from decimal import Decimal

from extensions import db
from models import PurchaseOrder, PurchaseOrderLine
from money import money, money_sum, rate, to_decimal
from roles import APPROVALS_ACT, role_allows

logger = logging.getLogger(__name__)

# Default numbering: PO-0001, PO-0002… Organizations with their own scheme can
# supply any number they like; this is only what we reach for when they do not.
NUMBER_PREFIX = "PO-"
NUMBER_PAD = 4
_NUMBER_RE = re.compile(r"^PO-(\d+)$")

MAX_LINES = 500
HUNDRED = Decimal("100")


# ─── Arithmetic ──────────────────────────────────────────────────────────────
def compute_line(quantity, unit_price, tax_rate) -> tuple[Decimal, Decimal, Decimal]:
    """Return (subtotal, tax, total) for one line, each rounded to 2dp.

    Rounded here rather than at the end of the order: see rule 2 above.
    """
    qty = to_decimal(quantity) or Decimal("0")
    price = to_decimal(unit_price) or Decimal("0")
    rate_pct = to_decimal(tax_rate) or Decimal("0")

    subtotal = money(qty * price) or Decimal("0.00")
    tax = money(subtotal * rate_pct / HUNDRED) or Decimal("0.00")
    return subtotal, tax, subtotal + tax


def recompute_totals(po: PurchaseOrder) -> None:
    """Rewrite the order's stored totals from its lines.

    Called on every write that can touch a line. The stored figures exist only
    so the list view can sort and filter in SQL; the lines are the truth.
    """
    po.subtotal = money_sum(line.line_subtotal for line in po.lines)
    po.tax_total = money_sum(line.tax_amount for line in po.lines)
    # Summed from the line totals rather than subtotal + tax_total so the
    # figure cannot drift from what the lines themselves add up to.
    po.total = money_sum(line.line_total for line in po.lines)


# ─── Numbering ───────────────────────────────────────────────────────────────
def next_po_number(organization_id: str) -> str:
    """The next PO-NNNN for this organization.

    Derived from the highest existing number rather than a counter column, so
    it stays correct if rows are imported or a draft is cancelled. Two
    simultaneous creates can land on the same number; the unique constraint
    catches that and the caller retries, which is cheaper and safer than
    locking a sequence table on every create.
    """
    rows = (
        db.session.query(PurchaseOrder.po_number)
        .filter(PurchaseOrder.organization_id == organization_id)
        .all()
    )
    highest = 0
    for (number,) in rows:
        match = _NUMBER_RE.match((number or "").strip().upper())
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{NUMBER_PREFIX}{highest + 1:0{NUMBER_PAD}d}"


# ─── Lines ───────────────────────────────────────────────────────────────────
def validate_lines(payload) -> tuple[list[dict], dict]:
    """Normalize incoming line data.

    Returns (clean, errors). Errors are keyed per line as `lines.0.quantity`
    so the client can mark the offending cell rather than showing one message
    for the whole form.
    """
    errors: dict[str, str] = {}
    if payload is None:
        return [], errors
    if not isinstance(payload, list):
        return [], {"lines": "Expected a list of line items."}
    if len(payload) > MAX_LINES:
        return [], {"lines": f"An order can hold at most {MAX_LINES} lines."}

    clean: list[dict] = []
    for index, raw in enumerate(payload):
        prefix = f"lines.{index}"
        if not isinstance(raw, dict):
            errors[prefix] = "Expected an object."
            continue

        description = str(raw.get("description") or "").strip()
        if not description:
            errors[f"{prefix}.description"] = "Describe what is being ordered."

        # rate() quantizes to 4dp, matching the Numeric(18,4) columns, so a
        # client sending more precision than the column holds is rounded here
        # rather than differently by each database engine.
        quantity = rate(raw.get("quantity"))
        if quantity is None:
            errors[f"{prefix}.quantity"] = "A quantity is required."
        elif quantity <= 0:
            # Zero would be a line that orders nothing; negative belongs on a
            # credit note, not a purchase order.
            errors[f"{prefix}.quantity"] = "Quantity must be greater than zero."

        unit_price = rate(raw.get("unitPrice"))
        if unit_price is None:
            errors[f"{prefix}.unitPrice"] = "A unit price is required."
        elif unit_price < 0:
            errors[f"{prefix}.unitPrice"] = "A unit price cannot be negative."

        tax_rate = rate(raw.get("taxRate"))
        if tax_rate is None:
            tax_rate = Decimal("0")
        if tax_rate < 0 or tax_rate > HUNDRED:
            errors[f"{prefix}.taxRate"] = "Tax rate must be between 0 and 100."

        clean.append({
            "description": description[:500],
            "sku": (str(raw.get("sku")).strip()[:120] if raw.get("sku") else None),
            "unit": (str(raw.get("unit")).strip()[:40] if raw.get("unit") else None),
            "quantity": quantity,
            "unitPrice": unit_price,
            "taxRate": tax_rate,
        })

    return clean, errors


def replace_lines(po: PurchaseOrder, clean: list[dict]) -> None:
    """Replace the order's lines with `clean` and recompute the totals.

    Wholesale replacement rather than a per-line diff: the client edits the
    order as one form, and matching a submitted line back to a stored one
    without stable client-side ids guesses wrong sooner or later. Safe only
    because edits are confined to drafts — nothing downstream references a
    draft's line ids yet.
    """
    po.lines.clear()
    for position, item in enumerate(clean, start=1):
        subtotal, tax, total = compute_line(
            item["quantity"], item["unitPrice"], item["taxRate"]
        )
        po.lines.append(PurchaseOrderLine(
            organization_id=po.organization_id,
            line_no=position,
            description=item["description"],
            sku=item["sku"],
            unit=item["unit"],
            quantity=item["quantity"],
            unit_price=item["unitPrice"],
            tax_rate=item["taxRate"],
            line_subtotal=subtotal,
            tax_amount=tax,
            line_total=total,
        ))
    recompute_totals(po)


# ─── Lifecycle ───────────────────────────────────────────────────────────────
class TransitionError(Exception):
    """A status change the lifecycle does not allow."""

    def __init__(self, message: str, code: str = "INVALID_TRANSITION"):
        super().__init__(message)
        self.message = message
        self.code = code


def approver_count(organization_id: str) -> int:
    """How many members of this organization can approve.

    Needed for the segregation-of-duties rule below, which has to behave
    differently for a one-person organization than for a finance team.
    """
    from models import OrganizationMembership

    rows = (
        db.session.query(OrganizationMembership.role)
        .filter(OrganizationMembership.organization_id == organization_id)
        .all()
    )
    return sum(1 for (role,) in rows if role_allows(role, APPROVALS_ACT))


def check_can_approve(po: PurchaseOrder, user_id: str) -> None:
    """Segregation of duties: you do not approve your own order.

    Raising and approving the same commitment is the classic internal-control
    failure, and a product that exists to impose financial discipline should
    not be the place it happens. The exception is an organization where the
    actor is the only member who can approve at all — refusing there would make
    approval impossible rather than safer, so the rule relaxes instead of
    locking a solo user out of their own workflow.
    """
    if po.created_by_user_id != user_id:
        return
    if approver_count(po.organization_id) > 1:
        raise TransitionError(
            "You cannot approve an order you raised yourself. Ask another "
            "approver in your organization to review it.",
            code="SELF_APPROVAL",
        )


def transition(po: PurchaseOrder, status: str, *, user_id: str | None = None,
               reason: str | None = None) -> None:
    """Move `po` to `status`, stamping whatever that status records.

    The single doorway for status changes, so the lifecycle cannot be bypassed
    by a handler that sets `po.status` directly.
    """
    if status not in PurchaseOrder.STATUSES:
        raise TransitionError(f"'{status}' is not a purchase-order status.",
                              code="UNKNOWN_STATUS")
    if status == po.status:
        raise TransitionError(f"This order is already {status.replace('_', ' ')}.",
                              code="NO_CHANGE")
    if not po.can_transition_to(status):
        raise TransitionError(
            f"An order that is {po.status.replace('_', ' ')} cannot become "
            f"{status.replace('_', ' ')}.",
        )

    now = datetime.utcnow()
    previous = po.status

    if status == PurchaseOrder.PENDING_APPROVAL:
        if not po.lines:
            raise TransitionError(
                "Add at least one line before submitting this order for approval.",
                code="NO_LINES",
            )
        po.submitted_at = now
        # Clearing the old reason on resubmission: leaving it would show the
        # previous rejection against an order that is now awaiting a fresh
        # decision.
        po.rejection_reason = None
        po.rejected_at = None

    elif status == PurchaseOrder.APPROVED:
        if user_id:
            check_can_approve(po, user_id)
        po.approved_at = now
        po.approved_by_user_id = user_id

    elif status == PurchaseOrder.DRAFT and previous == PurchaseOrder.PENDING_APPROVAL:
        # A rejection. The reason is kept so the person correcting the order
        # knows what to change.
        po.rejected_at = now
        po.rejection_reason = (reason or "").strip()[:500] or None

    elif status == PurchaseOrder.SENT:
        po.sent_at = now

    elif status == PurchaseOrder.CLOSED:
        po.closed_at = now

    elif status == PurchaseOrder.CANCELLED:
        po.cancelled_at = now

    po.status = status
