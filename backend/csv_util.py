"""Flatten an invoice into a QuickBooks-compatible CSV string.

Column names use QuickBooks bill/invoice terminology (Bill No, Bill Date, Due
Date, Terms, Description, Qty, Rate, Amount, …) so the file maps cleanly in
QuickBooks Online's CSV import wizard with little or no remapping.
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


def receipt_to_csv(rec: dict) -> str:
    """Flatten a receipt into an expense/QuickBooks-friendly CSV string."""
    merchant = rec.get("merchant") or {}
    base = [
        merchant.get("name"), merchant.get("address"),
        rec.get("receipt_date"), rec.get("receipt_number"),
        rec.get("payment_method"), rec.get("category"), rec.get("currency"),
    ]
    summary = [rec.get("subtotal"), rec.get("tax"), rec.get("tip"), rec.get("total")]

    items = rec.get("line_items") or [
        {"description": "", "quantity": None, "unit_price": None, "amount": None}
    ]

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(RECEIPT_HEADERS)
    for idx, item in enumerate(items):
        row = base + [
            item.get("description"), item.get("quantity"),
            item.get("unit_price"), item.get("amount"),
        ]
        row += summary if idx == 0 else ["", "", "", ""]
        writer.writerow(["" if v is None else v for v in row])

    return out.getvalue()


def invoice_to_csv(inv: dict) -> str:
    vendor = inv.get("vendor") or {}
    base = [
        vendor.get("name"), vendor.get("address"), vendor.get("email"),
        inv.get("invoice_number"), inv.get("invoice_date"), inv.get("due_date"),
        inv.get("currency"), inv.get("payment_terms"),
    ]
    summary = [inv.get("subtotal"), inv.get("tax"), inv.get("total")]

    items = inv.get("line_items") or [
        {"description": "", "quantity": None, "unit_price": None, "amount": None}
    ]

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(HEADERS)
    for idx, item in enumerate(items):
        row = base + [
            item.get("description"),
            item.get("quantity"),
            item.get("unit_price"),
            item.get("amount"),
        ]
        # Only put summary totals on the first row to avoid double counting.
        row += summary if idx == 0 else ["", "", ""]
        writer.writerow(["" if v is None else v for v in row])

    return out.getvalue()
