"""QuickBooks-compatible CSV export."""
import csv
import io

import openpyxl

from csv_util import HEADERS, RECEIPT_HEADERS, STATEMENT_HEADERS, invoice_to_csv, receipt_to_csv
from xlsx_util import document_to_xlsx


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
    """QuickBooks maps columns by header NAME, not position, so this asserts the
    vocabulary rather than a fixed prefix - otherwise adding a column breaks the
    test without breaking the export."""
    assert {
        "Vendor", "Vendor Address", "Vendor Email",
        "Bill No", "Bill Date", "Due Date", "Currency", "Terms",
        "Description", "Qty", "Rate", "Amount",
        "Subtotal", "Tax", "Total",
    } <= set(HEADERS)


def test_headers_cover_the_full_extracted_field_set():
    """Every field the extractor now captures should be exportable; a field that
    is extracted but never reaches the user's spreadsheet is invisible work."""
    assert {
        "Vendor Phone", "Vendor Tax ID", "Invoice Type", "PO Reference",
        "Customer", "Customer Tax ID", "Product", "Line Discount", "Tax Rate",
        "Discount", "Tax %", "Shipping", "Other Charges",
        "Amount Paid", "Balance Due",
    } <= set(HEADERS)


def test_every_row_matches_the_header_width():
    """A short row silently shifts every later column in the spreadsheet."""
    from csv_util import invoice_rows
    for invoice in ({}, _invoice(), {"line_items": []}):
        headers, rows = invoice_rows(invoice)
        for row in rows:
            assert len(row) == len(headers)


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


def test_xlsx_export_valid_for_all_doc_types():
    inv = _invoice()
    receipt = {
        "merchant": {"name": "Cafe", "address": None}, "receipt_date": "2026-02-01",
        "receipt_number": "R1", "payment_method": "Cash", "category": "Meals", "currency": "USD",
        "line_items": [{"description": "Latte", "quantity": 1, "unit_price": 4, "amount": 4}],
        "subtotal": 4, "tax": 0.4, "tip": 1, "total": 5.4,
    }
    statement = {
        "transactions": [
            {"date": "2026-05-08", "description": "Airtime", "debit": 84, "credit": None, "balance": 0, "reference": "A1"},
        ],
    }
    cases = {
        "invoice": (inv, HEADERS),
        "receipt": (receipt, RECEIPT_HEADERS),
        "statement": (statement, STATEMENT_HEADERS),
    }
    for doc_type, (data, headers) in cases.items():
        blob = document_to_xlsx(doc_type, data)
        assert blob[:2] == b"PK", doc_type  # .xlsx is a zip archive
        wb = openpyxl.load_workbook(io.BytesIO(blob))
        ws = wb.active
        assert [c.value for c in ws[1]] == headers, doc_type
