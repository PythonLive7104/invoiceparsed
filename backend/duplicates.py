"""Duplicate invoice detection.

Paying the same invoice twice is the single most expensive clerical error in
accounts payable, and it is easy: a supplier emails a copy, someone forwards a
scan, the same PDF is uploaded from two machines.

Four rules, strongest first:

1. ``exact_file``      - identical bytes. Certain.
2. ``same_number``     - same supplier and same invoice number. Near certain;
                         an invoice number is meant to be unique per supplier.
3. ``same_amount_date``- same supplier, same total, same invoice date. Strong,
                         but genuinely possible twice in a day.
4. ``similar``         - same supplier and total, dates close together, or a
                         near-identical supplier name with the same number.
                         Weak; a prompt to look, nothing more.

Nothing here deletes, rejects or merges anything. A match is *recorded for a
human*, because the opposite error - refusing a legitimate invoice - is worse
than the one being prevented, and a supplier really can bill the same amount
twice in one day.

Detection is always scoped to one organization. A duplicate across tenants is
not a duplicate, it is a data leak.
"""
import hashlib
import re
from datetime import datetime
from decimal import Decimal

from models import Extraction
from money import to_decimal

# Rules, strongest first. Order matters: the first rule that fires for a pair
# is the one reported, so a pair is never listed twice with different wording.
EXACT_FILE = "exact_file"
SAME_NUMBER = "same_number"
SAME_AMOUNT_DATE = "same_amount_date"
SIMILAR = "similar"

RULE_ORDER = (EXACT_FILE, SAME_NUMBER, SAME_AMOUNT_DATE, SIMILAR)

SCORES = {EXACT_FILE: 1.0, SAME_NUMBER: 0.95, SAME_AMOUNT_DATE: 0.8, SIMILAR: 0.55}

# How many earlier documents to compare against. Detection runs inline on
# upload, so it is bounded; the exact-hash rule is an indexed lookup and is not
# subject to this limit.
COMPARISON_WINDOW = 500

# Dates this far apart still count as "around the same time" for the weak rule.
NEAR_DAYS = 5

# Company-form suffixes, stripped so "Acme Ltd" and "Acme Limited" compare
# equal. Not an attempt at legal-entity resolution - just the common noise.
_SUFFIXES = {
    "ltd", "limited", "llc", "inc", "incorporated", "plc", "gmbh", "bv", "nv",
    "sa", "srl", "pty", "co", "company", "corp", "corporation", "lp", "llp",
    "enterprises", "ventures", "holdings", "group", "services", "nigeria",
}


def file_hash(pages) -> str:
    """SHA-256 over the uploaded bytes.

    Multi-page uploads hash the concatenation in order, so the same pages in a
    different order are correctly NOT the same document.
    """
    digest = hashlib.sha256()
    for page in pages:
        digest.update(page["bytes"] if isinstance(page, dict) else page)
    return digest.hexdigest()


def normalize_supplier(name) -> str:
    """Reduce a supplier name to a comparable key.

    Lowercased, punctuation removed, company-form suffixes dropped. "ACME
    Supplies Ltd." and "acme supplies limited" both become "acme supplies".
    """
    if not isinstance(name, str):
        return ""
    cleaned = re.sub(r"[^a-z0-9\s]", " ", name.lower())
    words = [w for w in cleaned.split() if w and w not in _SUFFIXES]
    return " ".join(words)


def normalize_number(value) -> str:
    """Compare invoice numbers ignoring case and separators.

    "INV-2026-001", "inv2026001" and "INV 2026 001" are the same reference
    written three ways, and suppliers are not consistent about it.
    """
    if not isinstance(value, str):
        return ""
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _parse_date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip()[:10]).date()
    except ValueError:
        return None


def _amounts_equal(a, b) -> bool:
    left, right = to_decimal(a), to_decimal(b)
    if left is None or right is None:
        return False
    # A cent of tolerance: the same invoice can round differently if it was
    # re-extracted after a prompt change.
    return abs(left - right) <= Decimal("0.01")


def _fmt(value) -> str:
    parsed = to_decimal(value)
    return "—" if parsed is None else f"{parsed:,.2f}"


def _classify(new_row, other) -> tuple[str, str] | None:
    """Which rule fires for this pair, with its explanation. None if no match."""
    if (
        new_row.file_hash
        and other.file_hash
        and new_row.file_hash == other.file_hash
    ):
        return EXACT_FILE, (
            f"Byte-for-byte identical to '{other.file_name}', uploaded "
            f"{_when(other)}."
        )

    supplier_new = normalize_supplier(new_row.vendor_name)
    supplier_old = normalize_supplier(other.vendor_name)
    same_supplier = bool(supplier_new) and supplier_new == supplier_old

    number_new = normalize_number(new_row.invoice_number)
    number_old = normalize_number(other.invoice_number)
    same_number = bool(number_new) and number_new == number_old

    if same_supplier and same_number:
        return SAME_NUMBER, (
            f"{other.vendor_name} invoice {other.invoice_number} was already "
            f"uploaded {_when(other)} as '{other.file_name}'."
        )

    same_amount = _amounts_equal(new_row.total, other.total)
    date_new = _parse_date(new_row.invoice_date)
    date_old = _parse_date(other.invoice_date)

    if same_supplier and same_amount and date_new and date_new == date_old:
        return SAME_AMOUNT_DATE, (
            f"Same supplier, same amount ({_fmt(other.total)}) and same date "
            f"({other.invoice_date}) as '{other.file_name}'."
        )

    # Weak signals: same supplier and amount a few days apart, or the same
    # invoice number from a supplier whose name was read slightly differently.
    if same_supplier and same_amount and date_new and date_old:
        gap = abs((date_new - date_old).days)
        if gap <= NEAR_DAYS:
            return SIMILAR, (
                f"Same supplier and amount ({_fmt(other.total)}) as "
                f"'{other.file_name}', dated {gap} day(s) apart."
            )
    if same_number and supplier_new and supplier_old and not same_supplier:
        return SIMILAR, (
            f"Invoice number {other.invoice_number} matches '{other.file_name}', "
            f"but the supplier reads '{other.vendor_name}' there and "
            f"'{new_row.vendor_name}' here."
        )
    return None


def _when(row) -> str:
    return row.created_at.strftime("%d %b %Y") if row.created_at else "earlier"


def find_duplicates(new_row, *, organization_id, limit=COMPARISON_WINDOW) -> list[dict]:
    """Suspected duplicates of `new_row` within one organization.

    Returns dicts of {other, reason, score, detail}, strongest first, at most
    one entry per earlier document.
    """
    if not organization_id:
        return []

    candidates = (
        Extraction.query.filter(
            Extraction.organization_id == organization_id,
            Extraction.id != new_row.id,
            Extraction.deleted_at.is_(None),
            # A failed extraction has no reliable fields to compare.
            Extraction.status == "completed",
            Extraction.doc_type == new_row.doc_type,
        )
        .order_by(Extraction.created_at.desc())
        .limit(limit)
        .all()
    )

    matches = []
    for other in candidates:
        verdict = _classify(new_row, other)
        if verdict is None:
            continue
        reason, detail = verdict
        matches.append({
            "other": other,
            "reason": reason,
            "score": SCORES[reason],
            "detail": detail,
        })

    matches.sort(key=lambda m: (-m["score"], m["other"].created_at or datetime.min))
    return matches
