"""Canonical bank-statement schema (parallel to invoice/receipt) + validation.

`STATEMENT_JSON_SCHEMA` is handed to OpenAI's structured-output API; `normalize`
coerces model output into a predictable shape with all keys present.
"""

STATEMENT_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "account_holder": {"type": ["string", "null"]},
        "account_number": {"type": ["string", "null"]},
        "bank_name": {"type": ["string", "null"]},
        "currency": {
            "type": ["string", "null"],
            "description": "ISO 4217 currency code, e.g. USD, EUR, NGN",
        },
        "period_start": {"type": ["string", "null"], "description": "ISO 8601 (YYYY-MM-DD) if possible"},
        "period_end": {"type": ["string", "null"], "description": "ISO 8601 (YYYY-MM-DD) if possible"},
        "opening_balance": {"type": ["number", "null"]},
        "closing_balance": {"type": ["number", "null"]},
        "total_debit": {"type": ["number", "null"]},
        "total_credit": {"type": ["number", "null"]},
        "transactions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "date": {"type": ["string", "null"], "description": "ISO 8601 (YYYY-MM-DD) if possible"},
                    "description": {"type": "string"},
                    "debit": {"type": ["number", "null"], "description": "money out (positive number) or null"},
                    "credit": {"type": ["number", "null"], "description": "money in (positive number) or null"},
                    "balance": {"type": ["number", "null"], "description": "running balance after the transaction"},
                    "reference": {"type": ["string", "null"]},
                },
                "required": ["date", "description", "debit", "credit", "balance", "reference"],
            },
        },
        "confidence": {
            "type": "object",
            "description": "Self-assessed confidence 0..1 per field (1 = certain, ~0 = guessed/not found).",
            "additionalProperties": False,
            "properties": {
                "account_holder": {"type": "number"},
                "account_number": {"type": "number"},
                "bank_name": {"type": "number"},
                "currency": {"type": "number"},
                "period_start": {"type": "number"},
                "period_end": {"type": "number"},
                "opening_balance": {"type": "number"},
                "closing_balance": {"type": "number"},
                "total_debit": {"type": "number"},
                "total_credit": {"type": "number"},
                "transactions": {"type": "number"},
            },
            "required": [
                "account_holder", "account_number", "bank_name", "currency",
                "period_start", "period_end", "opening_balance", "closing_balance",
                "total_debit", "total_credit", "transactions",
            ],
        },
    },
    "required": [
        "account_holder", "account_number", "bank_name", "currency",
        "period_start", "period_end", "opening_balance", "closing_balance",
        "total_debit", "total_credit", "transactions", "confidence",
    ],
}

CONFIDENCE_FIELDS = (
    "account_holder", "account_number", "bank_name", "currency",
    "period_start", "period_end", "opening_balance", "closing_balance",
    "total_debit", "total_credit", "transactions",
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
    """Coerce model output into the canonical statement shape."""
    raw = raw or {}
    txns = raw.get("transactions") or []
    conf = raw.get("confidence") or {}

    return {
        "account_holder": raw.get("account_holder"),
        "account_number": raw.get("account_number"),
        "bank_name": raw.get("bank_name"),
        "currency": raw.get("currency"),
        "period_start": raw.get("period_start"),
        "period_end": raw.get("period_end"),
        "opening_balance": _num(raw.get("opening_balance")),
        "closing_balance": _num(raw.get("closing_balance")),
        "total_debit": _num(raw.get("total_debit")),
        "total_credit": _num(raw.get("total_credit")),
        "transactions": [
            {
                "date": (t or {}).get("date"),
                "description": (t or {}).get("description") or "",
                "debit": _num((t or {}).get("debit")),
                "credit": _num((t or {}).get("credit")),
                "balance": _num((t or {}).get("balance")),
                "reference": (t or {}).get("reference"),
            }
            for t in txns
        ],
        "confidence": {field: _conf_value(conf.get(field)) for field in CONFIDENCE_FIELDS},
    }
