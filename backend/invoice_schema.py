"""Canonical invoice schema + normalization.

`INVOICE_JSON_SCHEMA` is handed to OpenAI's structured-output API in strict
mode; `normalize` coerces any model output into a predictable shape with every
key present, money as `Decimal`, and confidence clamped to 0..1.

Two conventions worth knowing before editing:

* **Money is Decimal, never float.** See money.py. Quantities, unit prices and
  tax rates keep 4 decimal places because they are legitimately fractional;
  amounts are quantized to 2.
* **Confidence is a parallel object**, not a `{value, confidence}` wrapper
  around every field. OpenAI strict mode requires every property to appear in
  `required`, so wrapping each field would double the schema and force the
  model to emit a confidence for fields it never saw. A sibling object keeps
  the document readable and is what the UI already consumes.

Strict mode also forbids optional properties: every key must be listed in
`required` and be nullable instead. That is why nothing here is "optional" in
the JSON Schema sense — absent data is `null`.
"""
from money import money as _money
from money import rate as _rate

# ─── Reusable fragments ──────────────────────────────────────────────────────
_STR = {"type": ["string", "null"]}
_NUM = {"type": ["number", "null"]}


def _obj(**properties) -> dict:
    """An object whose properties are all required and nullable (strict mode)."""
    return {
        "type": ["object", "null"],
        "additionalProperties": False,
        "properties": properties,
        "required": list(properties),
    }


_PARTY = {
    "name": _STR,
    "address": _STR,
    "email": _STR,
    "phone": _STR,
    "tax_id": {**_STR, "description": "VAT / TIN / GST registration number"},
}

# ─── Schema ──────────────────────────────────────────────────────────────────
INVOICE_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        # Who issued the invoice.
        "vendor": _obj(
            **_PARTY,
            registration_number={**_STR, "description": "Company registration number"},
            bank_details=_obj(
                bank_name=_STR,
                account_name=_STR,
                account_number=_STR,
                iban=_STR,
                swift=_STR,
                sort_code=_STR,
            ),
        ),
        # Who it was issued to. Needed to tell an invoice you RECEIVED from one
        # you ISSUED, and later to match against the organization's own details.
        "customer": _obj(**_PARTY),

        "invoice_number": _STR,
        "invoice_type": {
            "type": ["string", "null"],
            "description": (
                "One of: invoice, credit_note, debit_note, proforma, receipt. "
                "A credit note reduces what is owed, so it must not be treated "
                "as a charge."
            ),
        },
        "purchase_order_reference": {
            **_STR,
            "description": "PO number referenced on the invoice, if any",
        },
        "invoice_date": {**_STR, "description": "ISO 8601 (YYYY-MM-DD) when possible"},
        "due_date": {**_STR, "description": "ISO 8601 (YYYY-MM-DD) when possible"},
        "currency": {**_STR, "description": "ISO 4217 code, e.g. USD, EUR, NGN"},
        "payment_terms": _STR,

        "line_items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "description": {"type": "string"},
                    "product_name": {
                        **_STR,
                        "description": "Product/service name or SKU, when distinct from the description",
                    },
                    "quantity": _NUM,
                    "unit_price": _NUM,
                    "discount": {**_NUM, "description": "Discount amount on this line"},
                    "tax_rate": {**_NUM, "description": "Tax percentage, e.g. 7.5 for 7.5%"},
                    "amount": {**_NUM, "description": "Line total after discount"},
                },
                "required": [
                    "description", "product_name", "quantity", "unit_price",
                    "discount", "tax_rate", "amount",
                ],
            },
        },

        # Totals.
        "subtotal": _NUM,
        "discount": {**_NUM, "description": "Invoice-level discount amount"},
        "tax": {**_NUM, "description": "Total tax/VAT amount"},
        "tax_percentage": {**_NUM, "description": "Headline tax rate, e.g. 20 for 20%"},
        "shipping": _NUM,
        "other_charges": _NUM,
        "total": _NUM,
        "amount_paid": _NUM,
        "balance_due": {
            **_NUM,
            "description": "Outstanding amount, when the invoice states one",
        },

        "confidence": {
            "type": "object",
            "description": (
                "Self-assessed confidence from 0 to 1 per field. 1 = certain and "
                "clearly legible; near 0 = guessed, inferred, or not found."
            ),
            "additionalProperties": False,
            "properties": {},  # filled in below
            "required": [],    # filled in below
        },
    },
    "required": [],  # filled in below
}

# Every field carries a confidence score except the score object itself.
CONFIDENCE_FIELDS = tuple(
    k for k in INVOICE_JSON_SCHEMA["properties"] if k != "confidence"
)

INVOICE_JSON_SCHEMA["properties"]["confidence"]["properties"] = {
    field: {"type": "number"} for field in CONFIDENCE_FIELDS
}
INVOICE_JSON_SCHEMA["properties"]["confidence"]["required"] = list(CONFIDENCE_FIELDS)
INVOICE_JSON_SCHEMA["required"] = list(INVOICE_JSON_SCHEMA["properties"])

# Document types we recognise. Anything else normalizes to "invoice".
INVOICE_TYPES = ("invoice", "credit_note", "debit_note", "proforma", "receipt")


# ─── Normalization ───────────────────────────────────────────────────────────
def _text(value):
    """Trim a string; None for anything empty or not a string."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _conf_value(value):
    """Clamp a confidence to 0..1, or None if it is not a number."""
    if value is None or value == "":
        return None
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return None


def _party(raw, *, with_extras=False) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    party = {
        "name": _text(raw.get("name")),
        "address": _text(raw.get("address")),
        "email": _text(raw.get("email")),
        "phone": _text(raw.get("phone")),
        "tax_id": _text(raw.get("tax_id")),
    }
    if with_extras:
        party["registration_number"] = _text(raw.get("registration_number"))
        bank = raw.get("bank_details")
        bank = bank if isinstance(bank, dict) else {}
        details = {
            "bank_name": _text(bank.get("bank_name")),
            "account_name": _text(bank.get("account_name")),
            "account_number": _text(bank.get("account_number")),
            "iban": _text(bank.get("iban")),
            "swift": _text(bank.get("swift")),
            "sort_code": _text(bank.get("sort_code")),
        }
        # An all-empty bank block is absent, not present-and-blank, so the UI
        # can hide the section instead of rendering a card full of dashes.
        party["bank_details"] = details if any(details.values()) else None
    return party


def _invoice_type(value) -> str:
    text = (_text(value) or "").lower().replace(" ", "_").replace("-", "_")
    return text if text in INVOICE_TYPES else "invoice"


def _line_item(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    return {
        "description": _text(raw.get("description")) or "",
        "product_name": _text(raw.get("product_name")),
        "quantity": _rate(raw.get("quantity")),
        "unit_price": _rate(raw.get("unit_price")),
        "discount": _money(raw.get("discount")),
        "tax_rate": _rate(raw.get("tax_rate")),
        "amount": _money(raw.get("amount")),
    }


def normalize(raw: dict) -> dict:
    """Coerce model output into the canonical invoice shape.

    Idempotent: running it over already-normalized data is a no-op, which is
    what lets stored payloads be re-read through it (documents.load_document).
    """
    raw = raw if isinstance(raw, dict) else {}
    items = raw.get("line_items")
    items = items if isinstance(items, list) else []
    conf = raw.get("confidence")
    conf = conf if isinstance(conf, dict) else {}

    return {
        "vendor": _party(raw.get("vendor"), with_extras=True),
        "customer": _party(raw.get("customer")),
        "invoice_number": _text(raw.get("invoice_number")),
        "invoice_type": _invoice_type(raw.get("invoice_type")),
        "purchase_order_reference": _text(raw.get("purchase_order_reference")),
        "invoice_date": _text(raw.get("invoice_date")),
        "due_date": _text(raw.get("due_date")),
        "currency": _text(raw.get("currency")),
        "payment_terms": _text(raw.get("payment_terms")),
        "line_items": [_line_item(item) for item in items],
        "subtotal": _money(raw.get("subtotal")),
        "discount": _money(raw.get("discount")),
        "tax": _money(raw.get("tax")),
        "tax_percentage": _rate(raw.get("tax_percentage")),
        "shipping": _money(raw.get("shipping")),
        "other_charges": _money(raw.get("other_charges")),
        "total": _money(raw.get("total")),
        "amount_paid": _money(raw.get("amount_paid")),
        "balance_due": _money(raw.get("balance_due")),
        "confidence": {f: _conf_value(conf.get(f)) for f in CONFIDENCE_FIELDS},
    }
