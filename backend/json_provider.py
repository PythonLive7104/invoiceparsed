"""JSON serialization for monetary values.

Flask's default provider raises on `Decimal`. The obvious fix — convert to
`float` — would defeat the point of storing money as Decimal at all, because
every JavaScript client reads a JSON number back as an IEEE-754 double. A
response carrying `0.1` arrives as `0.1000000000000000055511151231257827`, and
any client-side arithmetic compounds it.

So Decimal is serialized as a *decimal string*: `"19.99"`, not `19.99`. That is
what Stripe and most financial APIs do, and it round-trips exactly.
`Intl.NumberFormat.prototype.format()` accepts a decimal string directly
(ECMA-402 "Intl.NumberFormat V3"), so the frontend formats money for display
without ever creating a float.

Amounts that reach here are already quantized by money.py; the `"f"` format is
only to guarantee plain notation, since `str(Decimal("1E+3"))` would otherwise
emit `"1E+3"`.
"""
from decimal import Decimal

from flask.json.provider import DefaultJSONProvider


def _default(obj):
    if isinstance(obj, Decimal):
        # format(..., "f") never uses scientific notation, which no client
        # would parse as an amount.
        return format(obj, "f")
    return DefaultJSONProvider.default(obj)


class DecimalJSONProvider(DefaultJSONProvider):
    """Flask JSON provider that renders Decimal as an exact decimal string."""

    default = staticmethod(_default)


def dumps(obj, **kwargs) -> str:
    """json.dumps that understands Decimal, for the paths that bypass Flask.

    Two places need this: the extracted payload persisted to
    Extraction.data, and webhook delivery bodies. Both must agree with what the
    API returns, or an invoice would read differently over a webhook than over
    the REST endpoint.
    """
    import json

    return json.dumps(obj, default=_default, **kwargs)
