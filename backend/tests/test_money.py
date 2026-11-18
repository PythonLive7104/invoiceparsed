"""Exact decimal money handling.

Everything downstream (validation tolerances, PO matching, reconciliation)
compares amounts, so these are the tests that stop a float from sneaking back
in and manufacturing discrepancies.
"""
from decimal import Decimal

import pytest

from money import RATE_PLACES, as_json, money, money_sum, rate, to_decimal


# ─── The reason this module exists ───────────────────────────────────────────
def test_float_pipeline_would_drift_but_decimal_does_not():
    """Three 0.10 line items. In float they total 0.30000000000000004, which is
    not 0.30 — so a tolerance check against a stated 0.30 sees a discrepancy
    that is not on the document. (Ten of them happen to cancel their errors and
    land on 1.0 exactly, which is precisely why float drift is so hard to spot
    by eye.)"""
    assert sum([0.1] * 3) != 0.3
    assert money_sum(["0.10"] * 3) == Decimal("0.30")

    # Rounding a float disagrees with rounding the decimal: 2.675 is really
    # 2.67499999... in binary, so Python rounds it down to 2.67 while the
    # invoice says 2.68.
    assert round(2.675, 2) == 2.67
    assert money("2.675") == Decimal("2.68")


def test_float_input_does_not_inherit_binary_error():
    """Decimal(0.1) carries the full binary error; we must go through str()."""
    assert to_decimal(0.1) == Decimal("0.1")
    assert Decimal(0.1) != Decimal("0.1")  # what we are avoiding


def test_line_items_sum_to_stated_total_exactly():
    items = ["19.99", "5.01", "100.00", "0.07", "3.93"]
    assert money_sum(items) == money("129.00")


# ─── Parsing ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("raw,expected", [
    ("123.45", "123.45"),
    (123.45, "123.45"),
    (123, "123.00"),
    (Decimal("123.45"), "123.45"),
    ("  123.45  ", "123.45"),
    ("$123.45", "123.45"),
    ("€123.45", "123.45"),
    ("₦ 1,234.56", "1234.56"),     # naira with thousands separator
    ("1,234.56", "1234.56"),            # comma thousands, dot decimal
    ("1.234,56", "1234.56"),            # European: roles swapped
    ("1,234,567.89", "1234567.89"),
    ("1,234", "1234.00"),               # comma thousands, no decimals
    ("123,45", "123.45"),               # decimal comma
    ("-123.45", "-123.45"),
    ("(123.45)", "-123.45"),            # accounting negative
    ("(1,234.56)", "-1234.56"),
    ("(-5)", "-5.00"),                  # both markers: negative once, not twice
    ("+123.45", "123.45"),
    ("0", "0.00"),
    ("0.00", "0.00"),
])
def test_money_parsing(raw, expected):
    assert money(raw) == Decimal(expected)


@pytest.mark.parametrize("raw", [
    None, "", "   ", "abc", "N/A", "-", "$", "--5", {}, [], object(),
    True, False,          # bool is an int subclass; True must not become 1.00
    "NaN", "Infinity", "-Infinity",  # Decimal() accepts these; amounts must not
])
def test_unparseable_values_are_none(raw):
    assert money(raw) is None


def test_unparseable_value_does_not_raise():
    """A field we cannot read is missing data for validation to report, not an
    exception that kills an otherwise good extraction."""
    assert to_decimal("not a number") is None


# ─── Rounding ────────────────────────────────────────────────────────────────
def test_rounds_half_up_not_bankers():
    """Python's default is banker's rounding, which would make this 2.67."""
    assert money("2.675") == Decimal("2.68")
    assert money("2.665") == Decimal("2.67")


def test_money_quantizes_to_two_places():
    assert money("1.005") == Decimal("1.01")
    assert money("1.0049") == Decimal("1.00")


def test_rate_keeps_four_places():
    """Quantities and unit prices are legitimately fractional."""
    assert rate("0.0825") == Decimal("0.0825")
    assert rate("3.5") == Decimal("3.5000")
    assert RATE_PLACES == Decimal("0.0001")


def test_sum_quantizes_once_at_the_end():
    """Three thirds of a cent should not each round up to a cent."""
    assert money_sum(["0.004", "0.004", "0.004"]) == Decimal("0.01")


# ─── Summing ─────────────────────────────────────────────────────────────────
def test_sum_ignores_missing_values():
    assert money_sum(["10.00", None, "5.50", "", "bad"]) == Decimal("15.50")


def test_sum_of_nothing_is_zero_not_none():
    assert money_sum([]) == Decimal("0.00")
    assert money_sum([None, None]) == Decimal("0.00")


def test_sum_handles_negatives():
    assert money_sum(["100.00", "-25.50"]) == Decimal("74.50")


# ─── JSON contract ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("raw,expected", [
    ("123.45", "123.45"),
    ("123.4", "123.40"),      # always two places, so clients need no padding
    (123, "123.00"),
    ("0", "0.00"),
    ("-5", "-5.00"),
    ("1234567.89", "1234567.89"),
    (None, None),
])
def test_as_json_is_an_exact_decimal_string(raw, expected):
    assert as_json(raw) == expected


def test_as_json_never_uses_scientific_notation():
    """str(Decimal('1E+3')) is '1E+3', which no client would parse as money."""
    assert as_json(Decimal("1E+3")) == "1000.00"
    assert as_json(Decimal("1E-4")) == "0.00"


def test_as_json_output_round_trips():
    for raw in ["0.01", "19.99", "1234567.89", "-0.05"]:
        assert money(as_json(raw)) == money(raw)
