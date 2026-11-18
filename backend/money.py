"""Exact monetary arithmetic.

Money is `Decimal` everywhere in this codebase: `Numeric` in the database,
`Decimal` in Python, and a decimal *string* in JSON.

The reason is that binary floating point cannot represent most decimal
fractions. `0.1 + 0.2` is `0.30000000000000004`, and summing a few dozen
invoice line items drifts from the figure printed on the document. For a
product that validates totals and flags discrepancies, that drift is not a
rounding detail — it manufactures false discrepancies and hides real ones.

Two rules keep this honest:

1. Never construct a Decimal from a float directly. `Decimal(0.1)` inherits the
   binary error in full; `Decimal(str(0.1))` does not. `to_decimal` always goes
   through `str`.
2. Quantize only at the edges (storage and display), never between arithmetic
   steps, so intermediate sums keep full precision.
"""
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

# Monetary values are stored and compared to 2 decimal places. Numeric(18, 4) in
# the database leaves headroom for currencies with more minor units and for
# unit prices quoted to 4 places, without changing how totals compare.
MONEY_PLACES = Decimal("0.01")

# Quantities and unit prices may legitimately be fractional (3.5 hours, a unit
# price of 0.0825), so they get more places than a total does.
RATE_PLACES = Decimal("0.0001")

# Stripped before parsing: currency symbols and the spacing used around them.
# Not an exhaustive list of world currency symbols — just what shows up on
# invoices we see, plus the non-breaking and thin spaces PDFs like to emit.
_STRIP = "$£€¥₦₹₩₽₺$¢ \t   "

# What a bare number may look like once the sign and separators are gone.
_DIGITS = re.compile(r"\d+(?:\.\d+)?|\.\d+")


def to_decimal(value, places: Decimal | None = None) -> Decimal | None:
    """Parse `value` into a Decimal, or None if it is absent or unparseable.

    Accepts what extraction and user edits actually produce: Decimals, ints,
    floats, and strings that may carry a currency symbol, thousands separators
    or accounting-style parentheses for negatives.

    Returns None rather than raising. A field we cannot read is missing data, to
    be reported as such by the validation engine — not an exception that takes
    down an extraction that was otherwise fine.

    `places` quantizes the result (ROUND_HALF_UP, the convention people expect
    on an invoice; Python's default is banker's rounding, which would round
    2.675 down and surprise everyone).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        # bool is a subclass of int; treating True as 1.00 is never intended.
        return None

    if isinstance(value, Decimal):
        parsed = value
    elif isinstance(value, int):
        parsed = Decimal(value)
    elif isinstance(value, float):
        # str() first: Decimal(0.1) would carry the full binary error.
        parsed = Decimal(str(value))
    elif isinstance(value, str):
        parsed = _parse_string(value)
        if parsed is None:
            return None
    else:
        return None

    if not parsed.is_finite():
        # NaN / Infinity are not amounts. They can arrive as the strings "NaN"
        # or "Infinity", which Decimal() accepts happily.
        return None

    if places is not None:
        try:
            parsed = parsed.quantize(places, rounding=ROUND_HALF_UP)
        except InvalidOperation:
            # Quantizing an absurdly large value overflows the context rather
            # than silently truncating it.
            return None
    return parsed


def _parse_string(raw: str) -> Decimal | None:
    """Parse a human/LLM-written number. Returns None if it is not one."""
    text = raw.strip()
    if not text:
        return None

    for char in _STRIP:
        text = text.replace(char, "")

    # Accounting negatives: "(1,234.56)" means -1234.56.
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1].strip()

    # Leading sign, kept aside so separator handling below sees digits only.
    sign = ""
    if text[:1] in "+-":
        sign, text = text[:1], text[1:]

    if not text:
        return None

    # Separators. The extraction prompts ask for plain numbers, so this is a
    # safety net for documents and hand edits that slip through:
    #   "1,234.56" -> both present: comma is the thousands separator.
    #   "1.234,56" -> both present, comma last: European; swap roles.
    #   "1,234"    -> comma only, groups of 3: thousands separator.
    #   "123,45"   -> comma only, 2 trailing digits: decimal comma.
    has_comma, has_dot = "," in text, "." in text
    if has_comma and has_dot:
        if text.rindex(",") > text.rindex("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif has_comma:
        head, _, tail = text.rpartition(",")
        if len(tail) == 3 and head and "," not in head:
            text = text.replace(",", "")      # 1,234
        elif len(tail) in (1, 2):
            text = text.replace(",", ".")     # 123,45
        else:
            text = text.replace(",", "")      # 1,234,567
    # By this point the sign and any separators have been handled, so what
    # remains must be plain digits with at most one decimal point. Checking
    # explicitly rather than relying on Decimal() to reject the rest: Decimal
    # accepts "NaN", "Infinity" and "1E5", and a second sign would slip through
    # as a negation ("--5" would come back as 5).
    if not _DIGITS.fullmatch(text):
        return None
    parsed = Decimal(text)
    # Parentheses and a leading "-" both mean negative; applying either once
    # avoids "(-5)" coming back positive.
    return -parsed if (negative or sign == "-") else parsed


def money(value) -> Decimal | None:
    """Parse a monetary amount, quantized to 2 places."""
    return to_decimal(value, MONEY_PLACES)


def rate(value) -> Decimal | None:
    """Parse a quantity / unit price / tax rate, quantized to 4 places."""
    return to_decimal(value, RATE_PLACES)


def money_sum(values) -> Decimal:
    """Total an iterable of amounts, ignoring the ones that are absent.

    Returns Decimal("0.00") for an empty or all-None input, so callers can
    compare against an extracted total without a None check. Sums at full
    precision and quantizes once at the end.
    """
    total = Decimal(0)
    for value in values:
        parsed = to_decimal(value)
        if parsed is not None:
            total += parsed
    return total.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def as_json(value) -> str | None:
    """Render an amount for JSON: an exact decimal string, or None.

    A string rather than a JSON number because JSON numbers are read back as
    IEEE-754 doubles by every JavaScript client, which would undo the precision
    this module exists to preserve. `Intl.NumberFormat.format()` accepts a
    decimal string directly, so the frontend formats it without going through
    a float at all.
    """
    parsed = to_decimal(value, MONEY_PLACES)
    return None if parsed is None else format(parsed, "f")
