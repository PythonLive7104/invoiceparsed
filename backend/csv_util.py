"""Flatten extracted documents into tabular rows, then CSV.

Column names use QuickBooks bill/invoice terminology (Bill No, Bill Date, Due
Date, Terms, …) so invoice files map cleanly in QuickBooks' CSV import. The row
builders are shared with the Excel (.xlsx) exporter (xlsx_util.py).
"""
import csv
import io

HEADERS = [
    "Vendor", "Vendor Address", "Vendor Email",
    "Bill No", "Bill Date", "Due Date", "Currency", "Terms",
    "Description", "Qty", "Rate", "Amount",
    "Subtotal", "Tax", "Total",
]

RECEIPT_HEADERS = [
    "Merchant", "Merchant Address", "Receipt Date", "Receipt No",
    "Payment Method", "Category", "Currency",
    "Description", "Qty", "Rate", "Amount",
    "Subtotal", "Tax", "Tip", "Total",
]

STATEMENT_HEADERS = ["Date", "Description", "Debit", "Credit", "Balance", "Reference"]


# ─── Row builders (header + rows), shared by CSV and XLSX exporters ───────────
def invoice_rows(inv: dict):
    vendor = inv.get("vendor") or {}
    base = [
        vendor.get("name"), vendor.get("address"), vendor.get("email"),
        inv.get("invoice_number"), inv.get("invoice_date"), inv.get("due_date"),
        inv.get("currency"), inv.get("payment_terms"),
    ]
    summary = [inv.get("subtotal"), inv.get("tax"), inv.get("total")]
    items = inv.get("line_items") or [{"description": "", "quantity": None, "unit_price": None, "amount": None}]
    rows = []
    for idx, item in enumerate(items):
        row = base + [item.get("description"), item.get("quantity"), item.get("unit_price"), item.get("amount")]
        row += summary if idx == 0 else ["", "", ""]  # totals only on first row
        rows.append(row)
    return HEADERS, rows


def receipt_rows(rec: dict):
    merchant = rec.get("merchant") or {}
    base = [
        merchant.get("name"), merchant.get("address"),
        rec.get("receipt_date"), rec.get("receipt_number"),
        rec.get("payment_method"), rec.get("category"), rec.get("currency"),
    ]
    summary = [rec.get("subtotal"), rec.get("tax"), rec.get("tip"), rec.get("total")]
    items = rec.get("line_items") or [{"description": "", "quantity": None, "unit_price": None, "amount": None}]
    rows = []
    for idx, item in enumerate(items):
        row = base + [item.get("description"), item.get("quantity"), item.get("unit_price"), item.get("amount")]
        row += summary if idx == 0 else ["", "", "", ""]
        rows.append(row)
    return RECEIPT_HEADERS, rows


def statement_rows(stmt: dict):
    rows = [
        [t.get("date"), t.get("description"), t.get("debit"), t.get("credit"), t.get("balance"), t.get("reference")]
        for t in (stmt.get("transactions") or [])
    ]
    return STATEMENT_HEADERS, rows


_ROW_BUILDERS = {"invoice": invoice_rows, "receipt": receipt_rows, "statement": statement_rows}


def rows_for(doc_type: str, data: dict):
    """Return (headers, rows) for a document type — shared by CSV and XLSX."""
    return _ROW_BUILDERS.get(doc_type, invoice_rows)(data)


def _to_csv(headers, rows) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(["" if v is None else v for v in row])
    return out.getvalue()


# ─── Public CSV exporters (kept for back-compat / callers) ────────────────────
def invoice_to_csv(inv: dict) -> str:
    return _to_csv(*invoice_rows(inv))


def receipt_to_csv(rec: dict) -> str:
    return _to_csv(*receipt_rows(rec))


def statement_to_csv(stmt: dict) -> str:
    return _to_csv(*statement_rows(stmt))
