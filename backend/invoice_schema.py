"""Canonical invoice schema (matches the PRD JSON contract) + validation.

`INVOICE_JSON_SCHEMA` is handed to OpenAI's structured-output API; `normalize`
coerces any model output into a predictable shape with all keys present.
"""

# JSON Schema passed to OpenAI response_format=json_schema (strict mode).
INVOICE_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "vendor": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "name": {"type": ["string", "null"]},
                "address": {"type": ["string", "null"]},
                "email": {"type": ["string", "null"]},
            },
            "required": ["name", "address", "email"],
        },
        "invoice_number": {"type": ["string", "null"]},
        "invoice_date": {
            "type": ["string", "null"],
            "description": "ISO 8601 date (YYYY-MM-DD) when possible",
        },
        "due_date": {
            "type": ["string", "null"],
            "description": "ISO 8601 date (YYYY-MM-DD) when possible",
        },
        "currency": {
            "type": ["string", "null"],
            "description": "ISO 4217 currency code, e.g. USD, EUR, GBP",
        },
        "payment_terms": {"type": ["string", "null"]},
        "line_items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "description": {"type": "string"},
                    "quantity": {"type": ["number", "null"]},
                    "unit_price": {"type": ["number", "null"]},
                    "amount": {"type": ["number", "null"]},
                },
                "required": ["description", "quantity", "unit_price", "amount"],
            },
        },
        "subtotal": {"type": ["number", "null"]},
        "tax": {"type": ["number", "null"]},
        "total": {"type": ["number", "null"]},
        "confidence": {
            "type": "object",
            "description": (
                "Self-assessed extraction confidence from 0 to 1 for each field "
                "(1 = certain it is correct, ~0 = guessed or not found)."
            ),
            "additionalProperties": False,
            "properties": {
                "vendor": {"type": "number"},
                "invoice_number": {"type": "number"},
                "invoice_date": {"type": "number"},
                "due_date": {"type": "number"},
                "currency": {"type": "number"},
                "payment_terms": {"type": "number"},
                "line_items": {"type": "number"},
                "subtotal": {"type": "number"},
                "tax": {"type": "number"},
                "total": {"type": "number"},
            },
            "required": [
                "vendor", "invoice_number", "invoice_date", "due_date",
                "currency", "payment_terms", "line_items", "subtotal", "tax", "total",
            ],
        },
    },
    "required": [
        "vendor",
        "invoice_number",
        "invoice_date",
        "due_date",
        "currency",
        "payment_terms",
        "line_items",
        "subtotal",
        "tax",
        "total",
        "confidence",
    ],
}

CONFIDENCE_FIELDS = (
    "vendor", "invoice_number", "invoice_date", "due_date", "currency",
    "payment_terms", "line_items", "subtotal", "tax", "total",
)


def _num(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _conf_value(value):
    """Clamp a confidence value to 0..1, or None if not a number."""
    if value is None or value == "":
        return None
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return None


def normalize(raw: dict) -> dict:
    """Coerce model output into the canonical invoice shape."""
    raw = raw or {}
    vendor = raw.get("vendor") or {}
    items = raw.get("line_items") or []
    conf = raw.get("confidence") or {}

    return {
        "vendor": {
            "name": vendor.get("name"),
            "address": vendor.get("address"),
            "email": vendor.get("email"),
        },
        "invoice_number": raw.get("invoice_number"),
        "invoice_date": raw.get("invoice_date"),
        "due_date": raw.get("due_date"),
        "currency": raw.get("currency"),
        "payment_terms": raw.get("payment_terms"),
        "line_items": [
            {
                "description": (it or {}).get("description") or "",
                "quantity": _num((it or {}).get("quantity")),
                "unit_price": _num((it or {}).get("unit_price")),
                "amount": _num((it or {}).get("amount")),
            }
            for it in items
        ],
        "subtotal": _num(raw.get("subtotal")),
        "tax": _num(raw.get("tax")),
        "total": _num(raw.get("total")),
        "confidence": {field: _conf_value(conf.get(field)) for field in CONFIDENCE_FIELDS},
    }
