"""Supplier matching and statistics.

Attaching an invoice to the right supplier is what makes everything after it
possible: "how much do we owe Acme", PO matching, payment tracking, spend by
supplier. Attaching it to the WRONG supplier is worse than leaving it
unattached, because the error is invisible — the totals simply come out wrong
and nothing looks broken.

So matching is conservative and ordered by how much evidence each signal
carries. Where there is doubt the invoice is left unattached for a human,
rather than guessed.
"""
from decimal import Decimal

from duplicates import normalize_supplier
from extensions import db
from models import Extraction, Supplier
from money import as_json

# How a supplier was attached, recorded for the UI and for debugging a wrong
# attribution later.
MATCH_TAX_ID = "tax_id"
MATCH_NAME = "name"
MATCH_MANUAL = "manual"


def match_key_for(name) -> str:
    """The normalized form used for lookups. Shared with duplicate detection so
    the two never disagree about whether two names are the same supplier."""
    return normalize_supplier(name)


def find_supplier(organization_id, *, name=None, tax_id=None):
    """The existing supplier this invoice belongs to, or None.

    Tax ID first: it is an exact, government-issued identifier, and two
    businesses cannot share one. A name match is strong but not certain - two
    unrelated "Acme Services" can exist - so it is only used when there is no
    tax ID to contradict it.
    """
    if tax_id:
        cleaned = tax_id.strip()
        if cleaned:
            found = Supplier.query.filter_by(
                organization_id=organization_id, tax_id=cleaned
            ).first()
            if found is not None:
                return found, MATCH_TAX_ID

    key = match_key_for(name)
    if key:
        found = Supplier.query.filter_by(
            organization_id=organization_id, match_key=key
        ).first()
        if found is not None:
            return found, MATCH_NAME

    return None, None


def upsert_from_invoice(organization_id, vendor: dict):
    """Find or create the supplier an extracted invoice came from.

    Returns (supplier, created). Returns (None, False) when the invoice carries
    no usable supplier name - a nameless supplier record is worse than none,
    because every later unnamed invoice would match it.
    """
    vendor = vendor if isinstance(vendor, dict) else {}
    name = (vendor.get("name") or "").strip()
    key = match_key_for(name)
    if not key:
        return None, False

    tax_id = (vendor.get("tax_id") or "").strip() or None
    existing, _how = find_supplier(organization_id, name=name, tax_id=tax_id)
    if existing is not None:
        # Fill in blanks from the invoice, but never overwrite what is already
        # recorded: a hand-corrected supplier record outranks whatever the
        # extractor read off the latest scan.
        _fill_blanks(existing, vendor)
        return existing, False

    supplier = Supplier(
        organization_id=organization_id,
        name=name[:200],
        match_key=key[:200],
        email=(vendor.get("email") or None),
        phone=(vendor.get("phone") or None),
        address=(vendor.get("address") or None),
        tax_id=tax_id,
        registration_number=(vendor.get("registration_number") or None),
    )
    _apply_bank(supplier, vendor.get("bank_details"))
    db.session.add(supplier)
    return supplier, True


def _fill_blanks(supplier, vendor: dict) -> None:
    for attribute, key in (
        ("email", "email"), ("phone", "phone"), ("address", "address"),
        ("tax_id", "tax_id"), ("registration_number", "registration_number"),
    ):
        if not getattr(supplier, attribute) and vendor.get(key):
            setattr(supplier, attribute, vendor[key])
    # Bank details are deliberately NOT auto-updated here. Silently replacing
    # payment instructions from a scanned document is exactly the mechanism
    # invoice-redirection fraud relies on; a change has to be made by a person.
    if not any([
        supplier.bank_name, supplier.bank_account_number,
        supplier.bank_iban, supplier.bank_swift,
    ]):
        _apply_bank(supplier, vendor.get("bank_details"))


def _apply_bank(supplier, bank) -> None:
    if not isinstance(bank, dict):
        return
    supplier.bank_name = bank.get("bank_name")
    supplier.bank_account_name = bank.get("account_name")
    supplier.bank_account_number = bank.get("account_number")
    supplier.bank_iban = bank.get("iban")
    supplier.bank_swift = bank.get("swift")
    supplier.bank_sort_code = bank.get("sort_code")


def attach_to_invoice(record, organization_id, document) -> None:
    """Attach a freshly extracted invoice to its supplier, creating one if new."""
    if record.doc_type != "invoice":
        return
    supplier, _created = upsert_from_invoice(
        organization_id, (document or {}).get("vendor")
    )
    if supplier is not None:
        db.session.flush()  # the supplier needs an id before it can be referenced
        record.supplier_id = supplier.id


# ─── Statistics ──────────────────────────────────────────────────────────────
def supplier_stats(supplier) -> dict:
    """Invoice totals for one supplier.

    Amounts are summed PER CURRENCY. A single total across mixed currencies is
    a meaningless number that looks authoritative, which is worse than showing
    nothing.
    """
    rows = (
        db.session.query(
            Extraction.currency,
            db.func.count(Extraction.id),
            db.func.sum(Extraction.total),
        )
        .filter(
            Extraction.supplier_id == supplier.id,
            Extraction.deleted_at.is_(None),
            Extraction.status == "completed",
        )
        .group_by(Extraction.currency)
        .all()
    )

    totals = [
        {
            "currency": currency or "—",
            "count": count,
            "total": as_json(total if total is not None else Decimal(0)),
        }
        for currency, count, total in rows
    ]
    totals.sort(key=lambda t: t["count"], reverse=True)

    return {
        "invoiceCount": sum(t["count"] for t in totals),
        "totalsByCurrency": totals,
        "lastInvoiceAt": _last_invoice_at(supplier),
    }


def _last_invoice_at(supplier):
    row = (
        Extraction.query.filter(
            Extraction.supplier_id == supplier.id,
            Extraction.deleted_at.is_(None),
        )
        .order_by(Extraction.created_at.desc())
        .first()
    )
    return row.created_at.isoformat() + "Z" if row and row.created_at else None


def possible_duplicate_suppliers(organization_id, limit=50) -> list:
    """Suppliers that look like the same business recorded twice.

    The unique constraint already prevents an exact normalized-name collision,
    so these are the softer signals: a shared tax ID, or one name contained in
    another ("Acme" vs "Acme Supplies").
    """
    rows = (
        Supplier.query.filter_by(organization_id=organization_id, status="active")
        .order_by(Supplier.name.asc())
        .limit(500)
        .all()
    )

    pairs, seen = [], set()
    by_tax_id = {}
    for supplier in rows:
        if supplier.tax_id:
            by_tax_id.setdefault(supplier.tax_id.strip(), []).append(supplier)

    for tax_id, group in by_tax_id.items():
        for first, second in _combinations(group):
            key = tuple(sorted((first.id, second.id)))
            if key in seen:
                continue
            seen.add(key)
            pairs.append({
                "reason": "same_tax_id",
                "detail": f"Both carry tax ID {tax_id}.",
                "suppliers": [first.public(), second.public()],
            })

    for first, second in _combinations(rows):
        key = tuple(sorted((first.id, second.id)))
        if key in seen or not first.match_key or not second.match_key:
            continue
        a, b = first.match_key, second.match_key
        if a != b and (a.startswith(b + " ") or b.startswith(a + " ")):
            seen.add(key)
            pairs.append({
                "reason": "similar_name",
                "detail": f"'{first.name}' and '{second.name}' may be the same business.",
                "suppliers": [first.public(), second.public()],
            })

    return pairs[:limit]


def _combinations(items):
    for index, first in enumerate(items):
        for second in items[index + 1:]:
            yield first, second
