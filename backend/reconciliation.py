"""Bank reconciliation: importing statement lines and matching them to payments.

Reconciliation answers one question — did the money we think we paid actually
leave the account, once, for the right amount? The ways it goes wrong are all
quiet: a payment recorded twice, a payment recorded and never made, a bank
charge sitting in "unmatched" for a year because nobody dared ignore it.

Four rules.

1. **The extraction pipeline is reused, not duplicated.** A statement that has
   already been read by `statement_schema` is imported straight from the
   stored payload. Re-parsing the same PDF with a second, worse parser would
   produce two answers about one document, and they would drift.

2. **Importing the same statement twice is harmless.** Every line carries a
   fingerprint, and a line already present is counted and skipped rather than
   duplicated. The count is reported, because "I imported 200 lines and 198
   appeared" is alarming unless the system says why.

3. **A suggestion is not a reconciliation.** The engine proposes; a person
   confirms. Only a confirmed match reconciles anything — the same rule as an
   unconfirmed invoice match not consuming an order's value.

4. **Ignoring is explicit and reasoned.** Bank charges, interest and transfers
   between an organization's own accounts are never going to match a supplier
   payment. They are set aside with a reason, so "unmatched" stays a short
   list of real problems rather than a wall people stop reading.
"""
import csv
import hashlib
import io
import logging
import re
from datetime import datetime
from decimal import Decimal

from extensions import db
from models import BankImport, BankMatch, BankTransaction, SupplierPayment
from money import money, to_decimal

logger = logging.getLogger(__name__)

ZERO = Decimal("0")
MAX_ROWS = 5000
MAX_CANDIDATES = 5

# How far apart a bank line and a payment may be and still be the same event.
DATE_WINDOW_DAYS = 5
# Amounts are compared exactly; a penny of slack covers rounding, not a
# genuine short payment.
AMOUNT_TOLERANCE = Decimal("0.01")

# Scores. Only a reference hit is strong enough to be worth presenting first;
# nothing here confirms itself, so these order a list rather than decide.
SCORE_REFERENCE = 1.0
SCORE_AMOUNT_DATE = 0.8
SCORE_AMOUNT = 0.5
SCORE_FUZZY = 0.4

_WORD = re.compile(r"[^a-z0-9]+")
# Noise every bank adds. Stripped before comparing descriptions so "BACS
# PAYMENT TO ACME LTD REF 9001" and "Acme Ltd" can be seen as the same party.
_BANK_NOISE = {
    "bacs", "chaps", "faster", "payment", "payments", "transfer", "transfers",
    "txn", "trf", "ref", "reference", "to", "from", "the", "ltd", "limited",
    "plc", "inc", "llc", "card", "direct", "debit", "credit", "online",
    "banking", "sent", "received", "value", "date",
}


class StatementImportError(Exception):
    """A statement that cannot be imported, with a code for the client."""

    def __init__(self, message: str, code: str = "INVALID_IMPORT"):
        super().__init__(message)
        self.message = message
        self.code = code


# ─── Normalizing ─────────────────────────────────────────────────────────────
def normalize_text(value) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(_WORD.sub(" ", value.lower()).split())


def meaningful_words(value) -> set[str]:
    """Description words that identify a party, with bank boilerplate removed."""
    return {
        word for word in normalize_text(value).split()
        if len(word) > 2 and word not in _BANK_NOISE
    }


def normalize_reference(value) -> str:
    """Compare references ignoring case and separators.

    "FT-9001", "ft9001" and "FT 9001" are one reference written three ways,
    and banks are not consistent about it.
    """
    if not isinstance(value, str):
        return ""
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _parse_date(value) -> str | None:
    """Coerce whatever the statement offered into an ISO date string.

    Banks export in every format there is. Day-first is tried before
    month-first for ambiguous values because this product's users are
    overwhelmingly outside the United States — and a date read the wrong way
    round silently moves a transaction by months, which is far worse than
    failing to read it at all.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if hasattr(value, "isoformat") and not isinstance(value, str):
        return value.isoformat()[:10]

    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
                "%m/%d/%Y", "%d %b %Y", "%d %B %Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:11].strip(), fmt).date().isoformat()
        except ValueError:
            continue
    # An ISO-ish prefix is better than nothing, and is what extraction emits.
    if re.match(r"^\d{4}-\d{2}-\d{2}", text):
        return text[:10]
    return None


def _days_between(first: str, second: str) -> int | None:
    try:
        a = datetime.fromisoformat(first[:10]).date()
        b = datetime.fromisoformat(second[:10]).date()
    except (TypeError, ValueError):
        return None
    return abs((a - b).days)


def fingerprint(organization_id: str, row: dict, position: int) -> str:
    """A stable identity for one statement line.

    Includes the row's position within its statement, because a bank really
    can issue two identical lines on one day — two £20 card payments to the
    same shop — and collapsing those would lose one of them.
    """
    parts = [
        organization_id,
        row.get("date") or "",
        normalize_text(row.get("description")),
        str(row.get("debit") or ""),
        str(row.get("credit") or ""),
        normalize_reference(row.get("reference")),
        str(position),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


# ─── Reading statements ──────────────────────────────────────────────────────
# Column names seen in the wild, mapped to what this module calls them. Matched
# on a normalized form, so "Value Date", "value_date" and "VALUE DATE" are one.
COLUMN_ALIASES = {
    "date": {"date", "transactiondate", "valuedate", "postingdate", "postdate",
             "bookingdate", "trandate"},
    "description": {"description", "details", "narrative", "particulars",
                    "transactiondetails", "memo", "payee", "remarks"},
    "reference": {"reference", "ref", "transactionreference", "chequenumber",
                  "cheque", "paymentreference"},
    "debit": {"debit", "withdrawal", "withdrawals", "moneyout", "paidout",
              "dr", "debitamount"},
    "credit": {"credit", "deposit", "deposits", "moneyin", "paidin", "cr",
               "creditamount"},
    "balance": {"balance", "runningbalance", "closingbalance"},
    "amount": {"amount", "value", "transactionamount"},
}


def _header_key(value) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def map_columns(headers: list) -> dict:
    """Which column holds what. Returns {field: index}."""
    found: dict[str, int] = {}
    for index, header in enumerate(headers):
        key = _header_key(header)
        for field, aliases in COLUMN_ALIASES.items():
            if key in aliases and field not in found:
                found[field] = index
    return found


def rows_from_csv(text: str) -> list[dict]:
    """Parse a bank CSV into transaction dicts.

    Handles the single-signed-amount layout as well as separate debit and
    credit columns: a negative amount is money out, which is the convention
    every bank that uses one column follows.
    """
    reader = csv.reader(io.StringIO(text))
    rows = [row for row in reader if any((cell or "").strip() for cell in row)]
    if not rows:
        raise StatementImportError("That file has no rows in it.", "EMPTY_FILE")

    # The header is the first row that maps to at least a date and one money
    # column; some exports put the account details above it.
    header_index, columns = None, {}
    for index, row in enumerate(rows[:10]):
        mapped = map_columns(row)
        if "date" in mapped and ({"debit", "credit"} & mapped.keys()
                                 or "amount" in mapped):
            header_index, columns = index, mapped
            break
    if header_index is None:
        raise StatementImportError(
            "Couldn't find the columns. The file needs a header row with a "
            "date and either an amount, or separate debit and credit columns.",
            "NO_HEADER",
        )

    def cell(row, field):
        index = columns.get(field)
        if index is None or index >= len(row):
            return None
        value = (row[index] or "").strip()
        return value or None

    out = []
    for row in rows[header_index + 1:][:MAX_ROWS]:
        debit = money(cell(row, "debit"))
        credit = money(cell(row, "credit"))
        if debit is None and credit is None and "amount" in columns:
            amount = money(cell(row, "amount"))
            if amount is not None:
                # One signed column: negative is money out.
                debit, credit = (-amount, None) if amount < 0 else (None, amount)

        date = _parse_date(cell(row, "date"))
        if date is None and debit is None and credit is None:
            continue

        out.append({
            "date": date,
            "description": cell(row, "description") or "",
            "reference": cell(row, "reference"),
            "debit": debit,
            "credit": credit,
            "balance": money(cell(row, "balance")),
        })
    if not out:
        raise StatementImportError("No transactions were found in that file.",
                           "NO_TRANSACTIONS")
    return out


def rows_from_xlsx(data: bytes) -> list[dict]:
    """Parse the first sheet of a workbook, through the same column mapping."""
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - openpyxl ships with the app
        raise StatementImportError(
            "Excel import is unavailable on this server.", "XLSX_UNAVAILABLE",
        ) from exc

    try:
        book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:
        raise StatementImportError("That file could not be opened as a workbook.",
                           "BAD_WORKBOOK") from exc

    sheet = book.worksheets[0]
    # Rendered back through the CSV reader so both formats go down one path
    # and cannot disagree about what a bank statement looks like.
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    for row in sheet.iter_rows(max_row=MAX_ROWS + 20, values_only=True):
        writer.writerow(["" if cell is None else str(cell) for cell in row])
    return rows_from_csv(buffer.getvalue())


def rows_from_statement(document: dict) -> list[dict]:
    """Transactions from a statement the extraction pipeline already read.

    Rule 1: this is the reuse. `statement_schema.normalize` has produced these
    fields already, and re-reading the PDF would be a second opinion about one
    document.
    """
    transactions = (document or {}).get("transactions") or []
    out = []
    for row in transactions[:MAX_ROWS]:
        if not isinstance(row, dict):
            continue
        out.append({
            "date": _parse_date(row.get("date")),
            "description": row.get("description") or "",
            "reference": row.get("reference"),
            "debit": money(row.get("debit")),
            "credit": money(row.get("credit")),
            "balance": money(row.get("balance")),
        })
    if not out:
        raise StatementImportError(
            "That statement has no transactions on it.", "NO_TRANSACTIONS",
        )
    return out


def store_rows(batch: BankImport, rows: list[dict]) -> tuple[int, int]:
    """Write rows, skipping any already present. Returns (imported, duplicates).

    Rule 2. Duplicates are counted rather than silently dropped.
    """
    existing = {
        row[0] for row in
        db.session.query(BankTransaction.fingerprint)
        .filter(BankTransaction.organization_id == batch.organization_id)
        .all()
    }
    imported = duplicates = 0
    seen_here: set[str] = set()

    for position, row in enumerate(rows):
        mark = fingerprint(batch.organization_id, row, position)
        if mark in existing or mark in seen_here:
            duplicates += 1
            continue
        seen_here.add(mark)
        db.session.add(BankTransaction(
            organization_id=batch.organization_id,
            bank_import_id=batch.id,
            txn_date=row.get("date"),
            description=(row.get("description") or "")[:500],
            reference=(row.get("reference") or None),
            debit=row.get("debit"),
            credit=row.get("credit"),
            balance=row.get("balance"),
            currency=batch.currency,
            fingerprint=mark,
        ))
        imported += 1

    batch.transaction_count = imported
    batch.duplicate_count = duplicates
    return imported, duplicates


# ─── Matching ────────────────────────────────────────────────────────────────
def outgoing_amount(txn: BankTransaction) -> Decimal | None:
    """What left the account on this line, or None if it is money coming in.

    Only outgoing lines match supplier payments. An inbound credit matched
    against a payment out would reconcile a refund as though it were the
    payment itself.
    """
    debit = to_decimal(txn.debit)
    if debit is not None and debit > 0:
        return debit
    credit = to_decimal(txn.credit)
    if credit is not None and credit < 0:
        # Some exports put outgoings in the credit column as negatives.
        return -credit
    return None


def score_pair(txn: BankTransaction, payment: SupplierPayment) -> tuple | None:
    """How strongly one bank line resembles one recorded payment, or None."""
    amount = outgoing_amount(txn)
    if amount is None:
        return None
    paid = to_decimal(payment.amount)
    if paid is None:
        return None

    difference = amount - paid
    close = abs(difference) <= AMOUNT_TOLERANCE

    # A matching reference is the strongest signal there is: it is the string
    # the payer typed and the bank carried through untouched.
    txn_ref = normalize_reference(txn.reference) or normalize_reference(
        txn.description
    )
    pay_ref = normalize_reference(payment.reference)
    if pay_ref and len(pay_ref) >= 4 and pay_ref in txn_ref:
        return (SCORE_REFERENCE, BankMatch.BY_REFERENCE, difference)

    if not close:
        # Without the amount agreeing, nothing below is evidence of anything.
        return None

    gap = _days_between(txn.txn_date or "", payment.paid_on or "")
    if gap is not None and gap <= DATE_WINDOW_DAYS:
        return (SCORE_AMOUNT_DATE, BankMatch.BY_AMOUNT_DATE, difference)

    shared = meaningful_words(txn.description)
    if shared:
        return (SCORE_FUZZY, BankMatch.BY_FUZZY, difference)

    return (SCORE_AMOUNT, BankMatch.BY_AMOUNT, difference)


def candidates_for(txn: BankTransaction, *, limit: int = MAX_CANDIDATES) -> list:
    """Recorded payments this bank line might be, strongest first.

    Payments already confirmed against another line are excluded: a payment
    that has been reconciled once cannot also be this.
    """
    taken = {
        row[0] for row in
        db.session.query(BankMatch.supplier_payment_id)
        .filter(
            BankMatch.organization_id == txn.organization_id,
            BankMatch.status == BankMatch.CONFIRMED,
            BankMatch.bank_transaction_id != txn.id,
        )
        .all()
    }
    payments = (
        SupplierPayment.query.filter(
            SupplierPayment.organization_id == txn.organization_id,
            SupplierPayment.voided_at.is_(None),
        )
        .limit(2000)
        .all()
    )

    scored = []
    for payment in payments:
        if payment.id in taken:
            continue
        result = score_pair(txn, payment)
        if result is None:
            continue
        score, method, difference = result
        scored.append({
            "payment": payment,
            "score": score,
            "method": method,
            "difference": difference,
        })
    # Negated score sorts descending while the id sorts ascending, so ties
    # break deterministically rather than on whatever the database returned.
    scored.sort(key=lambda entry: (-entry["score"], entry["payment"].id))
    return scored[:limit]


def suggest_for(txn: BankTransaction) -> BankMatch | None:
    """Record the engine's best guess for one line, if it has one.

    Suggested only. Rule 3: the engine proposes and a person confirms, because
    a plausible guess nobody checked is not evidence that money moved.
    """
    if txn.status != BankTransaction.UNMATCHED:
        return None
    existing = BankMatch.query.filter_by(bank_transaction_id=txn.id).first()
    if existing is not None:
        return existing

    best = candidates_for(txn, limit=1)
    if not best:
        return None

    entry = best[0]
    match = BankMatch(
        organization_id=txn.organization_id,
        bank_transaction_id=txn.id,
        supplier_payment_id=entry["payment"].id,
        status=BankMatch.SUGGESTED,
        method=entry["method"],
        score=entry["score"],
        difference=entry["difference"],
    )
    db.session.add(match)
    return match


def suggest_for_import(batch: BankImport) -> int:
    """Propose a match for every unmatched line in a batch."""
    count = 0
    for txn in batch.transactions:
        if suggest_for(txn) is not None:
            count += 1
    return count


def confirm(match: BankMatch, user_id: str, *, note: str | None = None) -> None:
    match.status = BankMatch.CONFIRMED
    match.confirmed_by_user_id = user_id
    match.confirmed_at = datetime.utcnow()
    if note:
        match.note = note[:500]
    txn = BankTransaction.query.filter_by(id=match.bank_transaction_id).first()
    if txn is not None:
        txn.status = BankTransaction.MATCHED


def unmatch(match: BankMatch) -> None:
    """Reject a match and put the bank line back in the unmatched list."""
    txn = BankTransaction.query.filter_by(id=match.bank_transaction_id).first()
    if txn is not None and txn.status == BankTransaction.MATCHED:
        txn.status = BankTransaction.UNMATCHED
    db.session.delete(match)


def reconciliation_summary(organization_id: str) -> dict:
    """Where the account stands, leading with what somebody has to deal with."""
    rows = (
        db.session.query(BankTransaction.status,
                         db.func.count(BankTransaction.id))
        .filter(BankTransaction.organization_id == organization_id)
        .group_by(BankTransaction.status)
        .all()
    )
    counts = {status: 0 for status in BankTransaction.STATUSES}
    for status, count in rows:
        if status in counts:
            counts[status] = count

    suggested = (
        db.session.query(db.func.count(BankMatch.id))
        .filter(
            BankMatch.organization_id == organization_id,
            BankMatch.status == BankMatch.SUGGESTED,
        )
        .scalar()
    ) or 0

    # Recorded payments with no confirmed bank line against them: money the
    # organization believes it has paid and the bank has not shown leaving.
    matched_payments = (
        db.session.query(BankMatch.supplier_payment_id)
        .filter(
            BankMatch.organization_id == organization_id,
            BankMatch.status == BankMatch.CONFIRMED,
        )
    )
    unreconciled = (
        db.session.query(db.func.count(SupplierPayment.id))
        .filter(
            SupplierPayment.organization_id == organization_id,
            SupplierPayment.voided_at.is_(None),
            SupplierPayment.id.notin_(matched_payments),
        )
        .scalar()
    ) or 0

    return {
        "byStatus": counts,
        "awaitingConfirmation": suggested,
        "unreconciledPayments": unreconciled,
        "total": sum(counts.values()),
    }
