"""Goods-receipt arithmetic, numbering and lifecycle.

The third leg of three-way matching. An order is a promise and an invoice is a
claim; a goods receipt is the only one of the three that says anything arrived.

Four rules are load-bearing.

1. **Accepted is what counts.** `accepted = received - damaged - rejected`, and
   `accepted` is the only figure matching measures an invoice against. You do
   not owe a supplier for goods you refused or for goods that arrived smashed,
   and a system that forgets that will happily pay for both.

2. **Only a posted receipt counts.** A half-entered delivery note in draft must
   not make an invoice payable. Identical in spirit to the rule that an
   unconfirmed invoice match does not consume an order's value.

3. **The totals on the order line are a cache with one writer.**
   `recompute_received` rewrites `quantity_received` and `quantity_accepted`
   from the posted receipts every time anything changes. Incrementing them
   would be cheaper and would drift the first time a receipt was cancelled or
   a quantity corrected — and a silently wrong "received to date" is worse
   than no column at all. The same discipline as
   `po_matching.recompute_invoiced`.

4. **Nothing is deleted.** A receipt recorded in error is cancelled. It is a
   record of a physical event somebody asserted at a point in time, and an
   invoice may already have been matched against it.
"""
import logging
import re
from datetime import datetime
from decimal import Decimal

from extensions import db
from models import GoodsReceipt, GoodsReceiptLine, PurchaseOrder
from money import rate, to_decimal

logger = logging.getLogger(__name__)

NUMBER_PREFIX = "GRN-"
NUMBER_PAD = 4
_NUMBER_RE = re.compile(r"^GRN-(\d+)$")

MAX_LINES = 500
ZERO = Decimal("0")

# Statuses of a purchase order that may receive goods. A draft or
# pending-approval order has not been placed with anybody, so nothing can have
# arrived against it; a cancelled one should not be accepting deliveries.
RECEIVABLE_PO_STATUSES = {
    PurchaseOrder.APPROVED,
    PurchaseOrder.SENT,
    PurchaseOrder.PARTIALLY_RECEIVED,
    PurchaseOrder.FULLY_RECEIVED,
}


class ReceiptError(Exception):
    """A receipt operation the rules do not allow, with a code for the client."""

    def __init__(self, message: str, code: str = "INVALID_RECEIPT"):
        super().__init__(message)
        self.message = message
        self.code = code


# ─── Numbering ───────────────────────────────────────────────────────────────
def next_grn_number(organization_id: str) -> str:
    """The next GRN number for this organization.

    Derived from the highest existing number rather than a counter column, so
    it stays correct if receipts are imported or one is cancelled. Collisions
    are possible under concurrency and are caught by the unique constraint and
    retried by the caller — cheaper and safer than locking a counter on every
    write. The same approach as purchase-order numbering.
    """
    highest = 0
    rows = (
        db.session.query(GoodsReceipt.grn_number)
        .filter(GoodsReceipt.organization_id == organization_id)
        .all()
    )
    for (number,) in rows:
        match = _NUMBER_RE.match(number or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{NUMBER_PREFIX}{highest + 1:0{NUMBER_PAD}d}"


# ─── Line arithmetic ─────────────────────────────────────────────────────────
def compute_accepted(received, damaged, rejected) -> Decimal:
    """What is actually owed for on one receipt line.

    Never negative: damaged plus rejected exceeding received is rejected by
    `validate_lines` at the edge, and clamping here as well means a row written
    by any other route cannot produce a negative "accepted" that would then be
    subtracted from an order's received total.
    """
    got = rate(received) or ZERO
    broken = rate(damaged) or ZERO
    refused = rate(rejected) or ZERO
    accepted = got - broken - refused
    return accepted if accepted > 0 else ZERO


def validate_lines(payload, po: PurchaseOrder) -> tuple[list, dict]:
    """Check client-supplied receipt lines against the order they claim to be for.

    Errors are keyed `lines.<index>.<field>` so the client can mark the exact
    cell rather than showing one message above the whole table.
    """
    errors: dict[str, str] = {}
    if not isinstance(payload, list):
        return [], {"lines": "Expected a list of lines."}
    if not payload:
        return [], {"lines": "Record at least one line."}
    if len(payload) > MAX_LINES:
        return [], {"lines": f"A receipt cannot have more than {MAX_LINES} lines."}

    by_id = {line.id: line for line in po.lines}
    clean: list[dict] = []
    seen: set[str] = set()

    for index, raw in enumerate(payload):
        if not isinstance(raw, dict):
            errors[f"lines.{index}"] = "Expected an object."
            continue

        po_line_id = (raw.get("purchaseOrderLineId") or "").strip()
        po_line = by_id.get(po_line_id)
        if po_line is None:
            errors[f"lines.{index}.purchaseOrderLineId"] = (
                "This line is not on that purchase order."
            )
            continue
        if po_line_id in seen:
            # Two receipt lines against one order line would make "how much of
            # line 3 arrived" ambiguous within a single delivery note.
            errors[f"lines.{index}.purchaseOrderLineId"] = (
                "This order line is already on this receipt."
            )
            continue
        seen.add(po_line_id)

        values = {}
        bad = False
        for key, field in (
            ("quantityReceived", "received"),
            ("quantityDamaged", "damaged"),
            ("quantityRejected", "rejected"),
        ):
            # `rate`, not `to_decimal`, so the value is quantized to the 4
            # places the column holds — a client sending more precision than
            # the column stores is rounded here rather than differently by
            # each database engine.
            parsed = rate(raw.get(key)) if raw.get(key) not in (None, "") else ZERO
            if parsed is None:
                errors[f"lines.{index}.{key}"] = "Enter a number."
                bad = True
                continue
            if parsed < 0:
                errors[f"lines.{index}.{key}"] = "Cannot be negative."
                bad = True
                continue
            values[field] = parsed
        if bad:
            continue

        if values["damaged"] + values["rejected"] > values["received"]:
            errors[f"lines.{index}.quantityDamaged"] = (
                "Damaged plus rejected cannot exceed what was received."
            )
            continue

        clean.append({
            "purchase_order_line_id": po_line_id,
            "line_no": po_line.line_no,
            "quantity_received": values["received"],
            "quantity_damaged": values["damaged"],
            "quantity_rejected": values["rejected"],
            "quantity_accepted": compute_accepted(
                values["received"], values["damaged"], values["rejected"]
            ),
            "notes": (raw.get("notes") or None),
        })

    if not clean and not errors:
        errors["lines"] = "Record at least one line."
    # Presented in order-line order rather than the order the client happened
    # to send them, so the receipt reads alongside the purchase order.
    clean.sort(key=lambda line: line["line_no"])
    return clean, errors


def replace_lines(receipt: GoodsReceipt, clean: list[dict]) -> None:
    """Swap a receipt's lines for a validated set.

    Wholesale replacement rather than a diff. Safe only because edits are
    confined to drafts: once a receipt is posted its lines are what invoices
    have been measured against.
    """
    receipt.lines.clear()
    for line in clean:
        receipt.lines.append(GoodsReceiptLine(
            organization_id=receipt.organization_id,
            purchase_order_line_id=line["purchase_order_line_id"],
            line_no=line["line_no"],
            quantity_received=line["quantity_received"],
            quantity_damaged=line["quantity_damaged"],
            quantity_rejected=line["quantity_rejected"],
            quantity_accepted=line["quantity_accepted"],
            notes=line["notes"],
        ))


# ─── What has been received against an order ─────────────────────────────────
def received_against(po: PurchaseOrder) -> dict:
    """Totals per order line from the POSTED receipts on `po`.

    Returns {"received": {line_id: Decimal}, "accepted": {line_id: Decimal},
    "receiptCount": int}. Summed in SQL rather than by loading every receipt,
    because this runs on every invoice comparison.
    """
    rows = (
        db.session.query(
            GoodsReceiptLine.purchase_order_line_id,
            # type_ stated explicitly: without it the aggregate can come back
            # from the driver as a float, and a float is exactly what the
            # Numeric columns exist to avoid.
            db.func.sum(GoodsReceiptLine.quantity_received,
                        type_=db.Numeric(18, 4)),
            db.func.sum(GoodsReceiptLine.quantity_accepted,
                        type_=db.Numeric(18, 4)),
        )
        .join(GoodsReceipt, GoodsReceipt.id == GoodsReceiptLine.goods_receipt_id)
        .filter(
            GoodsReceipt.purchase_order_id == po.id,
            GoodsReceipt.organization_id == po.organization_id,
            GoodsReceipt.status == GoodsReceipt.POSTED,
        )
        .group_by(GoodsReceiptLine.purchase_order_line_id)
        .all()
    )
    received = {line_id: to_decimal(got) or ZERO for line_id, got, _ in rows}
    accepted = {line_id: to_decimal(ok) or ZERO for line_id, _, ok in rows}

    count = (
        db.session.query(db.func.count(GoodsReceipt.id))
        .filter(
            GoodsReceipt.purchase_order_id == po.id,
            GoodsReceipt.organization_id == po.organization_id,
            GoodsReceipt.status == GoodsReceipt.POSTED,
        )
        .scalar()
    ) or 0

    return {"received": received, "accepted": accepted, "receiptCount": count}


def recompute_received(po: PurchaseOrder) -> None:
    """Refresh `quantity_received` and `quantity_accepted` on every order line.

    A cache with exactly one writer, for the reason given in rule 3 above.
    Also advances the order's status, because being delivered is a fact about
    the order and leaving it on `sent` after everything arrived would make the
    list lie.
    """
    position = received_against(po)
    for line in po.lines:
        line.quantity_received = position["received"].get(line.id, ZERO)
        line.quantity_accepted = position["accepted"].get(line.id, ZERO)
    _advance_status(po)


def _advance_status(po: PurchaseOrder) -> None:
    """Move the order to match what has arrived, where the rules allow it.

    Only ever moves an order that is open. A closed or cancelled order is not
    dragged back into an active state by a late delivery note, and an order
    still in draft or awaiting approval cannot be receiving goods at all.
    """
    if po.status not in RECEIVABLE_PO_STATUSES:
        return

    lines = list(po.lines)
    if not lines:
        return

    # "Fully received" means every line has at least as much ACCEPTED as was
    # ordered. Counting damaged goods toward completion would close an order
    # that still owes the organization a replacement.
    fully = all(
        (to_decimal(line.quantity_accepted) or ZERO)
        >= (to_decimal(line.quantity) or ZERO)
        for line in lines
    )
    any_received = any(
        (to_decimal(line.quantity_received) or ZERO) > 0 for line in lines
    )

    if fully:
        target = PurchaseOrder.FULLY_RECEIVED
    elif any_received:
        target = PurchaseOrder.PARTIALLY_RECEIVED
    else:
        # Everything was cancelled or returned. Fall back to `sent` only from a
        # received state, so an order that never left `approved` stays there.
        target = (
            PurchaseOrder.SENT
            if po.status in (PurchaseOrder.PARTIALLY_RECEIVED,
                             PurchaseOrder.FULLY_RECEIVED)
            else po.status
        )

    if target == po.status:
        return
    if po.can_transition_to(target):
        po.status = target
        return
    # Some moves are not in the table (fully_received back to partially, for
    # instance, after a receipt is cancelled). Reversing is legitimate here
    # because the physical facts changed, so it is applied directly - with the
    # guard above keeping it within the received/sent states.
    if target in (PurchaseOrder.SENT, PurchaseOrder.PARTIALLY_RECEIVED,
                  PurchaseOrder.FULLY_RECEIVED):
        po.status = target


# ─── Lifecycle ───────────────────────────────────────────────────────────────
def transition(receipt: GoodsReceipt, status: str, *, user_id=None,
               reason=None) -> None:
    """Move a receipt through its lifecycle, or raise `ReceiptError`.

    The single doorway. Nothing else sets `status` directly, so a receipt can
    never reach a state the rest of the system has no handling for.
    """
    if status not in GoodsReceipt.STATUSES:
        raise ReceiptError(f"'{status}' is not a receipt status.", "UNKNOWN_STATUS")
    if status == receipt.status:
        raise ReceiptError(f"This receipt is already {status}.", "NO_CHANGE")
    if not receipt.can_transition_to(status):
        raise ReceiptError(
            f"A {receipt.status} receipt cannot become {status}.",
            "INVALID_TRANSITION",
        )

    if status == GoodsReceipt.POSTED:
        if not receipt.lines:
            raise ReceiptError(
                "Add at least one line before posting this receipt.", "NO_LINES",
            )
        if not any(
            (to_decimal(line.quantity_received) or ZERO) > 0
            for line in receipt.lines
        ):
            # A receipt where nothing arrived is not a delivery; recording one
            # would advance an order's status on no evidence.
            raise ReceiptError(
                "This receipt records nothing as received.", "NOTHING_RECEIVED",
            )
        receipt.posted_at = datetime.utcnow()
        receipt.posted_by_user_id = user_id

    if status == GoodsReceipt.CANCELLED:
        receipt.cancelled_at = datetime.utcnow()
        receipt.cancelled_by_user_id = user_id
        receipt.cancellation_reason = (reason or None)

    receipt.status = status


def can_receive(po: PurchaseOrder) -> None:
    """Raise unless goods may be recorded against this order."""
    if po.status not in RECEIVABLE_PO_STATUSES:
        state = po.status.replace("_", " ")
        raise ReceiptError(
            f"Order {po.po_number} is {state}, so nothing can be received "
            "against it.",
            "PO_NOT_RECEIVABLE",
        )


def outstanding_lines(po: PurchaseOrder) -> list[dict]:
    """What is still owed on each line, for pre-filling a new receipt.

    Outstanding is measured against ACCEPTED, so goods that arrived damaged
    show as still outstanding — which is the truth: the supplier still owes
    those units or a credit.
    """
    out = []
    for line in po.lines:
        ordered = to_decimal(line.quantity) or ZERO
        accepted = to_decimal(line.quantity_accepted) or ZERO
        remaining = ordered - accepted
        out.append({
            "purchaseOrderLineId": line.id,
            "lineNo": line.line_no,
            "description": line.description,
            "sku": line.sku,
            "unit": line.unit,
            "quantityOrdered": ordered,
            "quantityAccepted": accepted,
            "quantityOutstanding": remaining if remaining > 0 else ZERO,
        })
    return out
