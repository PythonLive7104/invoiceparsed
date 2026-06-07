"""Canonical receipt schema (parallel to invoice_schema.py) + validation.

`RECEIPT_JSON_SCHEMA` is handed to OpenAI's structured-output API; `normalize`
coerces model output into a predictable shape with all keys present.
"""

RECEIPT_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "merchant": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "name": {"type": ["string", "null"]},
                "address": {"type": ["string", "null"]},
            },
            "required": ["name", "address"],
        },
        "receipt_date": {
            "type": ["string", "null"],
            "description": "ISO 8601 date (YYYY-MM-DD) when possible",
        },
        "receipt_number": {"type": ["string", "null"]},
        "payment_method": {
            "type": ["string", "null"],
            "description": "e.g. Visa ****1234, Cash, Mastercard, Amex, PayPal",
        },
        "category": {
            "type": ["string", "null"],
            "description": "Best-guess expense category, e.g. Meals, Travel, Office Supplies, Fuel",
        },
        "currency": {
            "type": ["string", "null"],
            "description": "ISO 4217 currency code, e.g. USD, EUR, GBP",
        },
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
        "tip": {"type": ["number", "null"]},
        "total": {"type": ["number", "null"]},
        "confidence": {
            "type": "object",
            "description": "Self-assessed confidence 0..1 per field (1 = certain, ~0 = guessed/not found).",
            "additionalProperties": False,
            "properties": {
                "merchant": {"type": "number"},
                "receipt_date": {"type": "number"},
                "receipt_number": {"type": "number"},
                "payment_method": {"type": "number"},
                "category": {"type": "number"},
                "currency": {"type": "number"},
                "line_items": {"type": "number"},
                "subtotal": {"type": "number"},
                "tax": {"type": "number"},
                "tip": {"type": "number"},
                "total": {"type": "number"},
            },
            "required": [
                "merchant", "receipt_date", "receipt_number", "payment_method",
                "category", "currency", "line_items", "subtotal", "tax", "tip", "total",
            ],
        },
    },
    "required": [
        "merchant", "receipt_date", "receipt_number", "payment_method", "category",
        "currency", "line_items", "subtotal", "tax", "tip", "total", "confidence",
    ],
}

CONFIDENCE_FIELDS = (
    "merchant", "receipt_date", "receipt_number", "payment_method", "category",
    "currency", "line_items", "subtotal", "tax", "tip", "total",
)


def _num(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _conf_value(value):
    if value is None or value == "":
        return None
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return None


def normalize(raw: dict) -> dict:
    """Coerce model output into the canonical receipt shape."""
    raw = raw or {}
    merchant = raw.get("merchant") or {}
    items = raw.get("line_items") or []
    conf = raw.get("confidence") or {}

    return {
        "merchant": {
            "name": merchant.get("name"),
            "address": merchant.get("address"),
        },
        "receipt_date": raw.get("receipt_date"),
        "receipt_number": raw.get("receipt_number"),
        "payment_method": raw.get("payment_method"),
        "category": raw.get("category"),
        "currency": raw.get("currency"),
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
        "tip": _num(raw.get("tip")),
        "total": _num(raw.get("total")),
        "confidence": {field: _conf_value(conf.get(field)) for field in CONFIDENCE_FIELDS},
    }
