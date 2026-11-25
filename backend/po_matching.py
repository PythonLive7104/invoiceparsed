"""Invoice-to-purchase-order matching.

The control this module implements is the oldest one in accounts payable: do
not pay for something nobody ordered, do not pay more than was agreed, and do
not pay for anything that never arrived. It answers three questions about an
incoming invoice — which order is this against, do the figures agree with that
order and with what was actually delivered, and is anything here serious enough
that it must not be paid until a person says so.

The third of those is **three-way matching** (P2.4): order, goods receipt and
invoice compared together. It switches itself on the first time an organization
posts a goods receipt, rather than from a setting somebody has to find. Without
that condition it would have to be either off by default — a control nobody
turns on — or on by default, which would block every invoice in every
organization that does not record deliveries.

Four rules shape everything below.

1. **Findings are computed, never trusted.** Every comparison is recomputed
   from the live document and the live order on each read, the way
   `validation.py` recomputes arithmetic. The cached verdict on
   `InvoiceMatch.outcome` exists so lists can filter in SQL, and is refreshed
   whenever it is recomputed. A figure corrected on the invoice changes the
   findings immediately; a stale snapshot would quietly keep an exception open
   or, worse, keep one closed.

2. **A weak signal suggests; it never decides.** A link is confirmed
   automatically only when the PO number on the document is an exact hit and
   the whole comparison comes back clean. Everything else waits for a person,
   because attaching an invoice to the wrong order corrupts the committed
   figure for both orders and nothing looks broken.

3. **Blocking is not refusing.** This module marks an invoice as "must not be
   approved without a human override" and records who overrode it and why. It
   never deletes, rejects or pays anything. A supplier really can invoice a
   price change that someone agreed over the phone.

4. **A finding names the numbers.** "Unit price 1,250.00 on the invoice,
   1,100.00 on the order (150.00 higher)" is actionable. "Price mismatch" sends
   someone hunting through two documents.

Line pairing is deterministic and pure: the same invoice against the same order
always pairs the same way. That is what lets `quantity_invoiced` be a cache
with a single writer (`recompute_invoiced`) rather than a running total that
can drift out of step with the documents it claims to summarize.
"""
import re
from datetime import datetime
from decimal import Decimal

from documents import load_document
from duplicates import normalize_number
from extensions import db
from goods_receipts import received_against
from models import (
    Extraction,
    GoodsReceipt,
    InvoiceMatch,
    MatchingSettings,
    PurchaseOrder,
)
from money import as_json, money, money_sum, rate, to_decimal

# ─── Severity ────────────────────────────────────────────────────────────────
# Deliberately not validation.py's error/review/warning. The question here is
# different: not "can this document be trusted" but "may this be paid".
BLOCKING = "blocking"   # must not be approved without an explicit override
REVIEW = "review"       # a person should look before it is paid
INFO = "info"           # worth knowing, not a problem

_SEVERITIES = (BLOCKING, REVIEW, INFO)

# How a paired line was recognised, strongest first.
BY_SKU = "sku"
BY_DESCRIPTION = "description"
BY_SIMILAR = "similar"

# Candidate scores. The gap between an exact PO number and everything else is
# wide on purpose: only the top of this scale may auto-confirm.
SCORE_PO_NUMBER = 1.0
SCORE_PO_NUMBER_LOOSE = 0.95
SCORE_PO_REFERENCE = 0.8
SCORE_SUPPLIER_AMOUNT = 0.5

# A candidate at or above this, found by PO number, may link itself.
AUTO_CONFIRM_SCORE = SCORE_PO_NUMBER_LOOSE

# Guards on the work any single request will do. A purchase order with more
# than this many invoices against it is not a case worth optimizing for, and an
# unbounded scan triggered by an upload is a denial-of-service waiting to be
# found.
MAX_CONFIRMED_SCAN = 200
MAX_CANDIDATE_SCAN = 500
MAX_CANDIDATES = 5
# Digit runs taken from a reference when narrowing the scan. Three covers
# "REQ-2026-0188-A"; beyond that the text is not a purchase order number.
MAX_DIGIT_RUNS = 3

HUNDRED = Decimal("100")
ZERO = Decimal("0")

_WORD = re.compile(r"[^a-z0-9]+")
_DIGITS = re.compile(r"\d+")


# ─── Settings ────────────────────────────────────────────────────────────────
def settings_for(organization_id: str) -> MatchingSettings:
    """This organization's tolerances, creating the defaults row on first use.

    Added to the session but not committed: the caller decides when, so reading
    settings inside a larger operation cannot half-commit it.
    """
    found = MatchingSettings.query.filter_by(
        organization_id=organization_id
    ).first()
    if found is not None:
        return found
    created = MatchingSettings(organization_id=organization_id)
    db.session.add(created)
    db.session.flush()
    return created


def within_tolerance(expected, actual, *, percent=None, amount=None) -> bool:
    """Is `actual` close enough to `expected`?

    Inside EITHER bound passes. Both are checked because a percentage is
    meaningless on a small figure and an absolute amount is meaningless on a
    large one; an organization sets whichever describes its tolerance and
    leaves the other at zero.
    """
    expected = to_decimal(expected) or ZERO
    actual = to_decimal(actual) or ZERO
    difference = abs(actual - expected)
    if difference == 0:
        return True
    limit = to_decimal(amount) or ZERO
    if limit > 0 and difference <= limit:
        return True
    share = to_decimal(percent) or ZERO
    if share > 0 and expected != 0:
        return difference <= abs(expected) * share / HUNDRED
    return False


# ─── Line pairing ────────────────────────────────────────────────────────────
def normalize_item(text) -> str:
    """Reduce a description or SKU to a comparable key.

    Separate from `duplicates.normalize_supplier`, which strips company-form
    suffixes: "Ltd" is noise in a business name and meaningful in a product
    description.
    """
    if not isinstance(text, str):
        return ""
    return " ".join(_WORD.sub(" ", text.lower()).split())


def _tokens(text: str) -> set[str]:
    # One- and two-character tokens are dropped: "x", "of" and "a" appear in
    # every description and would pair unrelated lines on nothing but filler.
    return {word for word in text.split() if len(word) > 2}


def _line_score(invoice_line: dict, po_line) -> tuple[float, str] | None:
    """How strongly one invoice line resembles one order line, or None."""
    inv_sku = normalize_item(invoice_line.get("product_name"))
    po_sku = normalize_item(po_line.sku)
    if inv_sku and po_sku and inv_sku == po_sku:
        return 1.0, BY_SKU

    inv_text = normalize_item(invoice_line.get("description"))
    po_text = normalize_item(po_line.description)
    if not inv_text or not po_text:
        return None
    if inv_text == po_text:
        return 0.9, BY_DESCRIPTION

    # A SKU written into the other side's description. Suppliers do this
    # constantly: the order says "HH-1003", the invoice says "Hydraulic hose
    # HH-1003, 1in x 3m".
    if po_sku and len(po_sku) > 3 and po_sku in inv_text:
        return 0.85, BY_SKU
    if inv_sku and len(inv_sku) > 3 and inv_sku in po_text:
        return 0.85, BY_SKU

    shorter, longer = sorted((inv_text, po_text), key=len)
    if len(shorter) >= 6 and shorter in longer:
        return 0.8, BY_SIMILAR

    inv_tokens, po_tokens = _tokens(inv_text), _tokens(po_text)
    if not inv_tokens or not po_tokens:
        return None
    shared = inv_tokens & po_tokens
    smaller = min(len(inv_tokens), len(po_tokens))
    if smaller < 2:
        # A single shared word is a coincidence, not an identification.
        return None

    # Coverage of the SHORTER description, not overlap of the two. Suppliers
    # abbreviate: the order says "Marine grease, lithium complex, 18kg pail"
    # and the invoice says "Marine grease 18kg". Measured as plain overlap that
    # pair scores 0.5, because the words the invoice left out count against it
    # - so an invoice being terser than the order would stop it matching at all.
    coverage = len(shared) / smaller
    # A floor on the overlap as well, so a description that merely STARTS the
    # same does not match: "red widget" covers all of itself inside "red widget
    # deluxe pro max edition", and those are not the same product.
    breadth = len(shared) / len(inv_tokens | po_tokens)
    if coverage >= 0.8 and breadth >= 0.4:
        return 0.6 + coverage / 10, BY_SIMILAR
    return None


def pair_lines(invoice_lines: list, po_lines: list) -> list[dict]:
    """Pair invoice lines to order lines, best evidence first.

    Greedy rather than optimal. An assignment algorithm would squeeze out a
    marginally better total score on a pathological order, at the cost of a
    pairing nobody can explain when they disagree with it — and on this data
    the greedy answer and the optimal answer differ only where both are
    guessing, which is exactly where a person should be looking anyway.

    Pure and deterministic: ties break on position, never on dictionary order.
    Returns one entry per invoice line, in document order, with `poLine` set to
    the paired order line or None.
    """
    scored = []
    for index, invoice_line in enumerate(invoice_lines):
        if not isinstance(invoice_line, dict):
            continue
        for po_line in po_lines:
            result = _line_score(invoice_line, po_line)
            if result is None:
                continue
            score, how = result
            # Negated score sorts descending while positions still sort
            # ascending, so the comparison is a plain tuple ordering.
            scored.append((-score, index, po_line.line_no, how, po_line))

    scored.sort()
    taken_invoice: dict[int, tuple] = {}
    taken_po: set[str] = set()
    for negative, index, _line_no, how, po_line in scored:
        if index in taken_invoice or po_line.id in taken_po:
            continue
        taken_invoice[index] = (po_line, how, -negative)
        taken_po.add(po_line.id)

    pairs = []
    for index, invoice_line in enumerate(invoice_lines):
        if not isinstance(invoice_line, dict):
            continue
        po_line, how, score = taken_invoice.get(index, (None, None, 0.0))
        pairs.append({
            "index": index,
            "invoiceLine": invoice_line,
            "poLine": po_line,
            "matchedBy": how,
            "score": score,
        })
    return pairs


# ─── What an order has already been invoiced ─────────────────────────────────
def invoiced_against(po, *, exclude_extraction_id: str | None = None) -> dict:
    """How much of `po` has already been invoiced, per line and in total.

    Counts CONFIRMED matches only. A suggestion nobody has looked at must not
    consume an order's remaining value, or one bad auto-suggestion would make
    every later invoice on that order look like over-invoicing.

    `exclude_extraction_id` leaves one invoice out, which is how an invoice is
    compared against what remains *excluding itself* — without it, a confirmed
    invoice would be measured against an order its own value had already used
    up.
    """
    confirmed = InvoiceMatch.query.filter(
        InvoiceMatch.purchase_order_id == po.id,
        InvoiceMatch.organization_id == po.organization_id,
        InvoiceMatch.status == InvoiceMatch.CONFIRMED,
    )
    # Counted before it is capped. A cap that quietly returns a smaller
    # figure would understate what has been invoiced, and understating that
    # is the one direction this function must never fail in - it is what
    # over-invoicing is measured against. Past the cap the caller is told
    # the figure is partial rather than handed a wrong one.
    truncated = confirmed.count() > MAX_CONFIRMED_SCAN
    rows = (
        confirmed.with_entities(InvoiceMatch.extraction_id)
        .limit(MAX_CONFIRMED_SCAN)
        .all()
    )
    ids = [row[0] for row in rows if row[0] != exclude_extraction_id]
    per_line: dict[str, Decimal] = {}
    total = ZERO
    count = 0
    if not ids:
        return {"perLine": per_line, "total": total, "invoiceCount": 0,
                "truncated": truncated}

    extractions = (
        Extraction.query.filter(
            Extraction.id.in_(ids),
            Extraction.deleted_at.is_(None),
        )
        .all()
    )
    po_lines = list(po.lines)
    for record in extractions:
        count += 1
        if record.total is not None:
            total += to_decimal(record.total) or ZERO
        document = load_document(record)
        if not document:
            continue
        for pair in pair_lines(document.get("line_items") or [], po_lines):
            po_line = pair["poLine"]
            if po_line is None:
                continue
            quantity = rate(pair["invoiceLine"].get("quantity")) or ZERO
            per_line[po_line.id] = per_line.get(po_line.id, ZERO) + quantity

    return {"perLine": per_line, "total": total, "invoiceCount": count,
            "truncated": truncated}


def recompute_invoiced(po) -> None:
    """Refresh `quantity_invoiced` on every line of `po`.

    The column is a cache with exactly one writer. Incrementing it as invoices
    arrive would be cheaper and would drift the first time a match was
    rejected, an invoice was deleted, or a quantity was corrected — and a
    silently wrong "invoiced to date" is worse than no column at all.

    Deliberately does NOT touch the order's status. Being invoiced is not being
    delivered; `partially_received` and `fully_received` are P2.4's to set from
    goods receipts, and moving an order on the strength of an invoice is how
    you end up having paid for goods that never arrived.
    """
    position = invoiced_against(po)["perLine"]
    for line in po.lines:
        line.quantity_invoiced = position.get(line.id, ZERO)


# ─── Finding candidates ──────────────────────────────────────────────────────
def _reference_candidates(organization_id: str, reference: str) -> list[dict]:
    """Orders whose number or reference matches the text on the invoice."""
    found: list[dict] = []
    seen: set[str] = set()
    cleaned = reference.strip()

    def add(po, method, score):
        if po.id in seen:
            return
        seen.add(po.id)
        found.append({"purchaseOrder": po, "method": method, "score": score})

    exact = PurchaseOrder.query.filter_by(
        organization_id=organization_id, po_number=cleaned.upper()
    ).first()
    if exact is not None:
        add(exact, InvoiceMatch.BY_PO_NUMBER, SCORE_PO_NUMBER)

    # Narrow the scan by the digit runs in the reference before comparing
    # normalized forms, so "PO-0042", "po 42" and "0042" reach the same order
    # without reading every order in the organization.
    #
    # One LIKE per run, OR'd together, rather than one pattern built from all
    # the digits joined: "REQ-2026-0188" has two runs, and a single "20260188"
    # pattern matches nothing at all because the stored reference has a hyphen
    # between them. Runs are digits only, so there is nothing in the pattern
    # that needs escaping.
    target = normalize_number(cleaned)
    runs = _DIGITS.findall(cleaned)[:MAX_DIGIT_RUNS]
    query = PurchaseOrder.query.filter_by(organization_id=organization_id)
    if runs:
        patterns = []
        for run in runs:
            patterns.append(PurchaseOrder.po_number.ilike(f"%{run}%"))
            patterns.append(PurchaseOrder.reference.ilike(f"%{run}%"))
        query = query.filter(db.or_(*patterns))
    rows = (
        query.order_by(PurchaseOrder.created_at.desc())
        .limit(MAX_CANDIDATE_SCAN)
        .all()
    )
    for po in rows:
        if target and normalize_number(po.po_number) == target:
            add(po, InvoiceMatch.BY_PO_NUMBER, SCORE_PO_NUMBER_LOOSE)
    for po in rows:
        if target and po.reference and normalize_number(po.reference) == target:
            add(po, InvoiceMatch.BY_PO_REFERENCE, SCORE_PO_REFERENCE)

    # Last: the same number written without its padding. "PO 42" for PO-0042 is
    # how people actually write these down, but it is genuinely ambiguous, so
    # this tier scores BELOW the auto-confirm threshold on purpose. It can
    # surface a suggestion for a person; it can never link anything by itself.
    if runs:
        # The longest run, which is the sequence number rather than a year or
        # a department code, compared numerically on both sides so that
        # padding stops mattering.
        wanted = int(max(runs, key=len))
        for po in rows:
            po_runs = _DIGITS.findall(po.po_number or "")
            if po_runs and int(max(po_runs, key=len)) == wanted:
                add(po, InvoiceMatch.BY_PO_NUMBER, SCORE_PO_REFERENCE)
    return found


def find_candidates(organization_id: str, document: dict, *,
                    supplier_id: str | None = None,
                    settings: MatchingSettings | None = None,
                    limit: int = MAX_CANDIDATES) -> list[dict]:
    """Orders this invoice might be billing, strongest evidence first.

    The PO number written on the document is the only signal strong enough to
    act on by itself. Supplier-and-amount is offered as a suggestion for a
    person to confirm, because two orders to the same supplier for the same
    amount are common and picking the wrong one is invisible.
    """
    document = document if isinstance(document, dict) else {}
    settings = settings or settings_for(organization_id)
    reference = (document.get("purchase_order_reference") or "").strip()

    found = _reference_candidates(organization_id, reference) if reference else []

    # Only where the invoice names no order at all. If it cites one and that
    # one cannot be found, suggesting a different order of the same value
    # papers over a serious finding - either the reference is wrong or
    # somebody is billing against an order they invented - and
    # `evaluate_unmatched` exists to report exactly that.
    if not found and not reference and supplier_id:
        invoice_total = money(document.get("total"))
        rows = (
            PurchaseOrder.query.filter(
                PurchaseOrder.organization_id == organization_id,
                PurchaseOrder.supplier_id == supplier_id,
                PurchaseOrder.status.in_(sorted(PurchaseOrder.OPEN_STATUSES)),
            )
            .order_by(PurchaseOrder.created_at.desc())
            .limit(MAX_CANDIDATE_SCAN)
            .all()
        )
        for po in rows:
            if invoice_total is None:
                continue
            if within_tolerance(
                po.total, invoice_total,
                percent=settings.total_tolerance_percent,
                amount=settings.total_tolerance_amount,
            ):
                found.append({
                    "purchaseOrder": po,
                    "method": InvoiceMatch.BY_SUPPLIER_AMOUNT,
                    "score": SCORE_SUPPLIER_AMOUNT,
                })

    found.sort(key=lambda entry: -entry["score"])
    return found[:limit]


# ─── Three-way matching ──────────────────────────────────────────────────────
def organization_uses_receipts(organization_id: str) -> bool:
    """Has this organization ever posted a goods receipt?

    What switches three-way matching on. Scoped to the organization rather
    than the single order, because the question is "do these people record
    deliveries" — if they do, an order with no receipt against it is a finding
    rather than a silence.

    Tested on `posted_at`, not on the current status, so the answer is "have
    you ever completed one" rather than "do you have one right now". Two
    consequences, both wanted: cancelling the last receipt does not quietly
    switch the control off — which would also make cancelling everything a way
    to disable it — and a draft somebody is halfway through typing does not
    switch it on.

    A cheap EXISTS, and it runs once per comparison.
    """
    return (
        db.session.query(GoodsReceipt.id)
        .filter(
            GoodsReceipt.organization_id == organization_id,
            GoodsReceipt.posted_at.isnot(None),
        )
        .first()
    ) is not None


def _receipt_findings(po, pairs, *, settings, delivery, uses_receipts) -> list[dict]:
    """Compare what is being invoiced against what was accepted.

    Measured against ACCEPTED, never against received: goods that arrived
    damaged or were sent back are not owed for, and an invoice that bills them
    is over-invoicing even though the lorry did turn up.
    """
    if not uses_receipts or not settings.require_goods_receipt:
        return []

    findings = []
    accepted_by_line = delivery["accepted"]

    if delivery["receiptCount"] == 0:
        # They record deliveries, and there is no record of one here.
        return [_finding(
            "invoice_before_goods", BLOCKING,
            f"Nothing has been recorded as received against order "
            f"{po.po_number}. Record the delivery, or accept this invoice "
            "explicitly if it is being paid in advance.",
            field="line_items",
        )]

    for pair in pairs:
        po_line = pair["poLine"]
        if po_line is None:
            continue
        invoice_qty = rate(pair["invoiceLine"].get("quantity"))
        if invoice_qty is None or invoice_qty <= 0:
            continue
        accepted = accepted_by_line.get(po_line.id, ZERO)
        line_no = pair["index"] + 1
        label = (pair["invoiceLine"].get("description") or "").strip()[:60] \
            or f"line {line_no}"

        if accepted <= 0:
            findings.append(_finding(
                "line_not_received", BLOCKING,
                f"{label}: invoiced for {_qty(invoice_qty)}, but none of this "
                "line has been accepted as delivered.",
                field="quantity", line_no=line_no,
            ))
            continue

        if within_tolerance(
            accepted, invoice_qty,
            percent=settings.quantity_tolerance_percent,
            amount=settings.quantity_tolerance_amount,
        ) or invoice_qty <= accepted:
            continue

        received = delivery["received"].get(po_line.id, ZERO)
        shortfall = invoice_qty - accepted
        detail = (
            f"{_qty(received)} arrived but only {_qty(accepted)} were accepted"
            if received > accepted
            else f"only {_qty(accepted)} have been accepted as delivered"
        )
        findings.append(_finding(
            "line_over_receipt", BLOCKING,
            f"{label}: invoiced for {_qty(invoice_qty)}, {detail} "
            f"({_qty(shortfall)} not delivered).",
            field="quantity", line_no=line_no,
        ))

    return findings


# ─── Comparison ──────────────────────────────────────────────────────────────
def _finding(code, severity, message, *, field=None, line_no=None) -> dict:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "field": field,
        "lineNo": line_no,
    }


def _fmt(value) -> str:
    parsed = to_decimal(value)
    return "—" if parsed is None else f"{parsed:,.2f}"


def _qty(value) -> str:
    """A quantity without trailing zeros: 3.0000 reads as 3, 2.5000 as 2.5."""
    parsed = to_decimal(value)
    if parsed is None:
        return "—"
    text = format(parsed, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _status_findings(po, settings) -> list[dict]:
    """Is this order in a state that may be invoiced at all?"""
    if po.status == PurchaseOrder.CANCELLED:
        return [_finding(
            "po_cancelled", BLOCKING,
            f"Order {po.po_number} was cancelled. Nothing should be invoiced "
            "against it.",
            field="status",
        )]
    if po.status in (PurchaseOrder.DRAFT, PurchaseOrder.PENDING_APPROVAL):
        state = "still a draft" if po.status == PurchaseOrder.DRAFT \
            else "waiting for approval"
        return [_finding(
            "po_not_approved",
            BLOCKING if settings.block_unapproved_po else REVIEW,
            f"Order {po.po_number} is {state}, so this spend was never "
            "authorized before it was incurred.",
            field="status",
        )]
    if po.status == PurchaseOrder.CLOSED:
        return [_finding(
            "po_closed", REVIEW,
            f"Order {po.po_number} is closed. A late invoice against a closed "
            "order is worth a second look.",
            field="status",
        )]
    return []


def _header_findings(po, document, *, settings, invoice_supplier_id) -> list[dict]:
    findings = _status_findings(po, settings)

    if invoice_supplier_id and po.supplier_id and invoice_supplier_id != po.supplier_id:
        findings.append(_finding(
            "supplier_mismatch", BLOCKING,
            f"This invoice is from a different supplier than order "
            f"{po.po_number} was placed with.",
            field="vendor",
        ))

    invoice_currency = (document.get("currency") or "").strip().upper()
    po_currency = (po.currency or "").strip().upper()
    if invoice_currency and po_currency and invoice_currency != po_currency:
        findings.append(_finding(
            "currency_mismatch", BLOCKING,
            f"Invoiced in {invoice_currency}, ordered in {po_currency}. The "
            "amounts cannot be compared, let alone paid.",
            field="currency",
        ))
    return findings


def _line_findings(pair, *, settings, outstanding) -> list[dict]:
    """Compare one paired invoice line against its order line."""
    invoice_line = pair["invoiceLine"]
    po_line = pair["poLine"]
    line_no = pair["index"] + 1
    label = (invoice_line.get("description") or "").strip()[:60] or f"line {line_no}"
    findings = []

    invoice_price = rate(invoice_line.get("unit_price"))
    po_price = rate(po_line.unit_price)
    if invoice_price is not None and po_price is not None and not within_tolerance(
        po_price, invoice_price,
        percent=settings.price_tolerance_percent,
        amount=settings.price_tolerance_amount,
    ):
        difference = invoice_price - po_price
        if difference > 0:
            findings.append(_finding(
                "line_price_higher", BLOCKING,
                f"{label}: invoiced at {_fmt(invoice_price)} a unit, ordered at "
                f"{_fmt(po_price)} ({_fmt(difference)} higher).",
                field="unit_price", line_no=line_no,
            ))
        else:
            # Charging less than agreed is not a problem to block a payment
            # over, but it is a figure worth seeing: it is just as often a line
            # paired with the wrong order line as it is a discount.
            findings.append(_finding(
                "line_price_lower", INFO,
                f"{label}: invoiced at {_fmt(invoice_price)} a unit, ordered at "
                f"{_fmt(po_price)} ({_fmt(abs(difference))} lower).",
                field="unit_price", line_no=line_no,
            ))

    invoice_qty = rate(invoice_line.get("quantity"))
    if invoice_qty is not None and not within_tolerance(
        outstanding, invoice_qty,
        percent=settings.quantity_tolerance_percent,
        amount=settings.quantity_tolerance_amount,
    ) and invoice_qty > outstanding:
        ordered = rate(po_line.quantity) or ZERO
        already = ordered - outstanding
        detail = (
            f"{_qty(already)} of {_qty(ordered)} already invoiced, so "
            f"{_qty(outstanding)} remained"
            if already > 0 else f"{_qty(ordered)} was ordered"
        )
        findings.append(_finding(
            "line_over_quantity", BLOCKING,
            f"{label}: invoiced for {_qty(invoice_qty)} but {detail}.",
            field="quantity", line_no=line_no,
        ))

    invoice_tax = rate(invoice_line.get("tax_rate"))
    po_tax = rate(po_line.tax_rate)
    if invoice_tax is not None and po_tax is not None and invoice_tax != po_tax:
        findings.append(_finding(
            "line_tax_mismatch", REVIEW,
            f"{label}: taxed at {_qty(invoice_tax)}%, ordered at "
            f"{_qty(po_tax)}%.",
            field="tax_rate", line_no=line_no,
        ))
    return findings


def _line_payload(pair, *, outstanding, expected_amount, received=None,
                  accepted_qty=None) -> dict:
    invoice_line = pair["invoiceLine"]
    po_line = pair["poLine"]
    data = {
        "lineNo": pair["index"] + 1,
        "description": invoice_line.get("description") or "",
        "productName": invoice_line.get("product_name"),
        "quantity": as_json(invoice_line.get("quantity")),
        "unitPrice": as_json(invoice_line.get("unit_price")),
        "taxRate": as_json(invoice_line.get("tax_rate")),
        "amount": as_json(invoice_line.get("amount")),
        "matchedBy": pair["matchedBy"],
        "matchScore": round(pair["score"], 3),
        "poLine": None,
    }
    if po_line is not None:
        data["poLine"] = {
            "id": po_line.id,
            "lineNo": po_line.line_no,
            "description": po_line.description,
            "sku": po_line.sku,
            "quantity": as_json(po_line.quantity),
            "unitPrice": as_json(po_line.unit_price),
            "taxRate": as_json(po_line.tax_rate),
            "quantityOutstanding": as_json(outstanding),
            "expectedAmount": as_json(expected_amount),
            # The delivery position for this line, so the client can show
            # ordered / received / accepted / invoiced side by side without a
            # second request.
            "quantityReceived": as_json(received),
            "quantityAccepted": as_json(accepted_qty),
        }
    return data


def compare(po, document: dict, *, settings=None,
            invoice_supplier_id: str | None = None,
            exclude_extraction_id: str | None = None) -> dict:
    """Compare one invoice against one purchase order.

    Returns the findings, the line-by-line pairing and the figures behind both,
    so the client renders the comparison rather than reconstructing it. Nothing
    is written: this is a read, and callers that want the verdict persisted
    pass the result to `apply_outcome`.
    """
    document = document if isinstance(document, dict) else {}
    settings = settings or settings_for(po.organization_id)
    po_lines = list(po.lines)

    findings = _header_findings(
        po, document, settings=settings, invoice_supplier_id=invoice_supplier_id
    )

    delivery = received_against(po)
    uses_receipts = organization_uses_receipts(po.organization_id)

    position = invoiced_against(po, exclude_extraction_id=exclude_extraction_id)
    already_invoiced = position["total"]
    po_total = to_decimal(po.total) or ZERO
    remaining = po_total - already_invoiced
    invoice_total = money(document.get("total"))

    invoice_lines = [
        item for item in (document.get("line_items") or []) if isinstance(item, dict)
    ]
    pairs = pair_lines(invoice_lines, po_lines)

    # What the invoiced quantities should cost at the prices on the order.
    # Rounded per line before summing, matching how the order itself was
    # totalled, so this figure can be compared with the invoice without a
    # rounding difference masquerading as a discrepancy.
    expected_parts = []
    line_payloads = []
    unpaired = 0
    for pair in pairs:
        po_line = pair["poLine"]
        if po_line is None:
            unpaired += 1
            line_payloads.append(_line_payload(pair, outstanding=None,
                                               expected_amount=None))
            continue
        ordered = rate(po_line.quantity) or ZERO
        outstanding = ordered - position["perLine"].get(po_line.id, ZERO)
        quantity = rate(pair["invoiceLine"].get("quantity")) or ZERO
        unit_price = rate(po_line.unit_price) or ZERO
        net = money(quantity * unit_price) or ZERO
        tax = money(net * (rate(po_line.tax_rate) or ZERO) / HUNDRED) or ZERO
        expected = net + tax
        expected_parts.append(expected)
        findings.extend(_line_findings(pair, settings=settings,
                                       outstanding=outstanding))
        line_payloads.append(_line_payload(
            pair, outstanding=outstanding, expected_amount=expected,
            received=delivery["received"].get(po_line.id, ZERO),
            accepted_qty=delivery["accepted"].get(po_line.id, ZERO),
        ))

    expected_total = money_sum(expected_parts)

    for pair in pairs:
        if pair["poLine"] is not None:
            continue
        line_no = pair["index"] + 1
        label = (pair["invoiceLine"].get("description") or "").strip()[:60] \
            or f"line {line_no}"
        findings.append(_finding(
            "line_not_on_po", BLOCKING,
            f"{label}: nothing on order {po.po_number} matches this line.",
            field="line_items", line_no=line_no,
        ))

    if not invoice_lines:
        findings.append(_finding(
            "no_invoice_lines", REVIEW,
            "The invoice has no line items, so only the total could be "
            "compared against the order.",
            field="line_items",
        ))

    if invoice_total is not None:
        if not within_tolerance(
            remaining, invoice_total,
            percent=settings.total_tolerance_percent,
            amount=settings.total_tolerance_amount,
        ) and invoice_total > remaining:
            detail = (
                f"{_fmt(already_invoiced)} of {_fmt(po_total)} has already been "
                f"invoiced, leaving {_fmt(remaining)}"
                if already_invoiced > 0
                else f"the order is for {_fmt(po_total)}"
            )
            findings.append(_finding(
                "total_over_po", BLOCKING,
                f"Invoiced {_fmt(invoice_total)} but {detail}. Over by "
                f"{_fmt(invoice_total - remaining)}.",
                field="total",
            ))
        elif invoice_total < remaining and expected_total > 0:
            findings.append(_finding(
                "partial_invoice", INFO,
                f"This invoice bills {_fmt(invoice_total)} of the "
                f"{_fmt(remaining)} outstanding on order {po.po_number}.",
                field="total",
            ))

        # A total above what the invoiced lines cost at order prices, even
        # where no single line price is out, catches a charge that was added
        # rather than a price that was changed.
        if expected_total > 0 and not unpaired and not within_tolerance(
            expected_total, invoice_total,
            percent=settings.total_tolerance_percent,
            amount=settings.total_tolerance_amount,
        ) and invoice_total > expected_total:
            findings.append(_finding(
                "total_above_order_prices", REVIEW,
                f"At the prices on order {po.po_number} the invoiced "
                f"quantities come to {_fmt(expected_total)}, but the invoice "
                f"totals {_fmt(invoice_total)} "
                f"({_fmt(invoice_total - expected_total)} more).",
                field="total",
            ))

    findings.extend(_receipt_findings(
        po, pairs, settings=settings, delivery=delivery,
        uses_receipts=uses_receipts,
    ))

    if position.get("truncated"):
        findings.append(_finding(
            "too_many_invoices", REVIEW,
            f"Order {po.po_number} already has more than "
            f"{MAX_CONFIRMED_SCAN} invoices against it, so the amount shown "
            "as already invoiced is incomplete and the remaining value "
            "cannot be relied on.",
            field="total",
        ))

    paired_ids = {
        pair["poLine"].id for pair in pairs if pair["poLine"] is not None
    }
    not_invoiced = [line for line in po_lines if line.id not in paired_ids]
    if not_invoiced and invoice_lines:
        findings.append(_finding(
            "lines_not_invoiced", INFO,
            f"{len(not_invoiced)} of {len(po_lines)} order "
            f"{'line is' if len(po_lines) == 1 else 'lines are'} not on this "
            "invoice, which is normal for a partial delivery.",
            field="line_items",
        ))

    counts = {severity: 0 for severity in _SEVERITIES}
    for finding in findings:
        if finding["severity"] in counts:
            counts[finding["severity"]] += 1

    if counts[BLOCKING]:
        outcome = InvoiceMatch.FAILED
    elif counts[REVIEW]:
        outcome = InvoiceMatch.DISCREPANCY
    else:
        outcome = InvoiceMatch.MATCHED

    return {
        "matched": True,
        "outcome": outcome,
        "findings": findings,
        "counts": counts,
        "lines": line_payloads,
        "poLinesNotInvoiced": [
            {
                "id": line.id,
                "lineNo": line.line_no,
                "description": line.description,
                "quantity": as_json(line.quantity),
                "unitPrice": as_json(line.unit_price),
            }
            for line in not_invoiced
        ],
        "totals": {
            "currency": po.currency,
            "invoiceCurrency": document.get("currency"),
            "invoiceTotal": as_json(invoice_total),
            "poTotal": as_json(po_total),
            "alreadyInvoiced": as_json(already_invoiced),
            "remainingBefore": as_json(remaining),
            "remainingAfter": as_json(
                remaining - (invoice_total if invoice_total is not None else ZERO)
            ),
            "expectedAtOrderPrices": as_json(expected_total),
            "otherInvoiceCount": position["invoiceCount"],
        },
        "delivery": {
            # Whether three-way matching applied at all, so the client can say
            # "not checked against deliveries" rather than implying it passed.
            "checked": bool(uses_receipts and settings.require_goods_receipt),
            "receiptCount": delivery["receiptCount"],
        },
    }


def evaluate_unmatched(organization_id: str, document: dict, *,
                       settings=None) -> dict:
    """What to report about an invoice that is not linked to any order.

    Two different situations, and conflating them would be a mistake. An
    invoice citing an order that does not exist is a serious finding: either
    the reference is wrong or somebody is billing against a purchase order they
    invented. An invoice citing nothing at all is ordinary for most spend, and
    only a finding where the organization has said every invoice must carry a
    PO.
    """
    document = document if isinstance(document, dict) else {}
    settings = settings or settings_for(organization_id)
    reference = (document.get("purchase_order_reference") or "").strip()
    findings = []

    if reference:
        findings.append(_finding(
            "po_not_found", BLOCKING,
            f"The invoice cites purchase order '{reference}', and no order of "
            "that number exists in this organization.",
            field="purchase_order_reference",
        ))
    else:
        findings.append(_finding(
            "no_po_reference",
            BLOCKING if settings.require_po_reference else REVIEW,
            "The invoice does not reference a purchase order, so there is "
            "nothing to check it against.",
            field="purchase_order_reference",
        ))

    counts = {severity: 0 for severity in _SEVERITIES}
    for finding in findings:
        counts[finding["severity"]] += 1
    result = {
        "matched": False,
        "outcome": InvoiceMatch.FAILED if counts[BLOCKING] else InvoiceMatch.DISCREPANCY,
        "findings": findings,
        "counts": counts,
        "lines": [],
        "poLinesNotInvoiced": [],
        "totals": {},
        "reference": reference or None,
    }
    # There is no match row here, so there is nothing anyone could have
    # overridden: a blocking finding blocks, full stop.
    result["blocked"] = is_blocked(None, result)
    return result


# ─── Persisting the verdict ──────────────────────────────────────────────────
def apply_outcome(match, comparison: dict) -> None:
    """Write the recomputed verdict back onto the match row.

    The row is a cache for filtering, so it is refreshed every time the
    comparison is recomputed rather than only when something is written. That
    is what keeps a list of exceptions honest after someone corrects a figure
    on an invoice.
    """
    match.outcome = comparison.get("outcome")
    counts = comparison.get("counts") or {}
    match.blocking_count = counts.get(BLOCKING, 0)
    match.review_count = counts.get(REVIEW, 0)


def is_blocked(match, comparison: dict) -> bool:
    """May this invoice be approved?

    The single question P2.5's approval engine asks of this module. A blocking
    finding stops an invoice unless a named person has accepted it in writing;
    an override does not make the finding go away, it records who owns it.
    """
    if (comparison.get("counts") or {}).get(BLOCKING, 0) == 0:
        return False
    return not (match is not None and match.is_overridden)


def evaluate(record, document: dict, *, settings=None, match=None,
             refresh: bool = True) -> dict:
    """The comparison for one extraction, matched or not.

    The entry point for anything that wants to know where an invoice stands:
    the match endpoints, the extraction payload, and the exception list. When
    `match` is omitted it is looked up; `refresh` writes the recomputed verdict
    back onto the row (the caller still commits).
    """
    settings = settings or settings_for(record.organization_id)
    if match is None:
        match = InvoiceMatch.query.filter_by(extraction_id=record.id).first()

    if match is None or match.status == InvoiceMatch.REJECTED:
        return evaluate_unmatched(
            record.organization_id, document, settings=settings
        )

    po = PurchaseOrder.query.filter_by(
        id=match.purchase_order_id, organization_id=record.organization_id
    ).first()
    if po is None:
        # The order behind a match cannot normally vanish (orders are cancelled,
        # never deleted), but a match pointing at nothing must read as an
        # exception rather than raise.
        return evaluate_unmatched(
            record.organization_id, document, settings=settings
        )

    comparison = compare(
        po, document,
        settings=settings,
        invoice_supplier_id=record.supplier_id,
        exclude_extraction_id=record.id,
    )
    comparison["blocked"] = is_blocked(match, comparison)
    if refresh:
        apply_outcome(match, comparison)
    return comparison


def auto_match(record, document: dict, *, settings=None) -> InvoiceMatch | None:
    """Link a freshly extracted invoice to its order, if the evidence allows.

    Called from the upload pipeline. Returns the match it created, or None when
    nothing credible was found — which is not a failure, it is the honest
    answer for most invoices.

    Only an exact PO number with a clean comparison confirms itself. Everything
    else is left as a suggestion for a person, because the cost of a wrong link
    is paid later and quietly.
    """
    if record.doc_type != "invoice":
        return None
    existing = InvoiceMatch.query.filter_by(extraction_id=record.id).first()
    if existing is not None:
        return existing

    settings = settings or settings_for(record.organization_id)
    candidates = find_candidates(
        record.organization_id, document,
        supplier_id=record.supplier_id, settings=settings,
    )
    if not candidates:
        return None

    best = candidates[0]
    po = best["purchaseOrder"]
    match = InvoiceMatch(
        organization_id=record.organization_id,
        extraction_id=record.id,
        purchase_order_id=po.id,
        status=InvoiceMatch.SUGGESTED,
        method=best["method"],
        score=best["score"],
        created_by_user_id=record.user_id,
    )
    db.session.add(match)

    comparison = compare(
        po, document,
        settings=settings,
        invoice_supplier_id=record.supplier_id,
        exclude_extraction_id=record.id,
    )
    apply_outcome(match, comparison)

    if (
        settings.auto_confirm_exact
        and best["method"] == InvoiceMatch.BY_PO_NUMBER
        and best["score"] >= AUTO_CONFIRM_SCORE
        and comparison["outcome"] == InvoiceMatch.MATCHED
    ):
        # confirmed_by_user_id stays None: the system confirmed this, and
        # recording the uploader as the person who approved the link would put
        # a name against a decision they never made.
        match.status = InvoiceMatch.CONFIRMED
        match.confirmed_at = datetime.utcnow()
        db.session.flush()
        recompute_invoiced(po)

    return match
