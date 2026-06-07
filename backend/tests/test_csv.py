"""QuickBooks-compatible CSV export."""
import csv
import io

from csv_util import invoice_to_csv, receipt_to_csv, HEADERS, RECEIPT_HEADERS


def _invoice():
    return {
        "vendor": {"name": "Acme Co", "address": "1 St", "email": "ar@acme.com"},
        "invoice_number": "INV-42", "invoice_date": "2026-01-10", "due_date": "2026-02-10",
        "currency": "USD", "payment_terms": "Net 30",
        "line_items": [
            {"description": "Design work", "quantity": 2, "unit_price": 100, "amount": 200},
            {"description": "Hosting", "quantity": 1, "unit_price": 20, "amount": 20},
        ],
        "subtotal": 220, "tax": 22, "total": 242,
    }


def test_headers_use_quickbooks_terminology():
    assert HEADERS[:8] == [
        "Vendor", "Vendor Address", "Vendor Email",
        "Bill No", "Bill Date", "Due Date", "Currency", "Terms",
    ]
    assert {"Description", "Qty", "Rate", "Amount", "Subtotal", "Tax", "Total"} <= set(HEADERS)


def test_one_row_per_line_item_totals_only_on_first():
    rows = list(csv.reader(io.StringIO(invoice_to_csv(_invoice()))))
    assert rows[0] == HEADERS
    assert len(rows) == 3  # header + 2 line items

    first, second = rows[1], rows[2]
    # Line-item detail present on each row.
    assert first[HEADERS.index("Description")] == "Design work"
    assert second[HEADERS.index("Qty")] == "1"
    # Totals only on the first row (avoids double counting on import).
    assert first[HEADERS.index("Total")] == "242"
    assert second[HEADERS.index("Total")] == ""


def test_receipt_csv_has_expense_columns():
    rec = {
        "merchant": {"name": "Cafe", "address": "5 St"},
        "receipt_date": "2026-02-01", "receipt_number": "R-9",
        "payment_method": "Visa ****1234", "category": "Meals", "currency": "USD",
        "line_items": [{"description": "Latte", "quantity": 2, "unit_price": 4, "amount": 8}],
        "subtotal": 8, "tax": 0.8, "tip": 1.5, "total": 10.3,
    }
    rows = list(csv.reader(io.StringIO(receipt_to_csv(rec))))
    assert rows[0] == RECEIPT_HEADERS
    assert {"Merchant", "Payment Method", "Category", "Tip"} <= set(RECEIPT_HEADERS)
    assert rows[1][RECEIPT_HEADERS.index("Merchant")] == "Cafe"
    assert rows[1][RECEIPT_HEADERS.index("Tip")] == "1.5"
