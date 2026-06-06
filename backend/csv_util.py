"""Flatten an invoice into a QuickBooks-friendly CSV string."""
import csv
import io

HEADERS = [
    "vendor_name", "vendor_address", "vendor_email",
    "invoice_number", "invoice_date", "due_date", "currency", "payment_terms",
    "line_description", "line_quantity", "line_unit_price", "line_amount",
    "subtotal", "tax", "total",
]


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
