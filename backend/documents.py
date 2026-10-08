"""Shared document helpers: original-file storage and headline-field mapping.

Extracted from routes/extract_routes.py so the anonymous demo + claim flow
(routes/demo_routes.py) stores files and denormalizes fields exactly the same
way a signed-in extraction does.
"""
import json
import mimetypes
import os

from werkzeug.utils import secure_filename

from config import Config
from invoice_schema import normalize as normalize_invoice
from receipt_schema import normalize as normalize_receipt
from statement_schema import normalize as normalize_statement

NORMALIZERS = {
    "invoice": normalize_invoice,
    "receipt": normalize_receipt,
    "statement": normalize_statement,
}


def normalize_for(doc_type: str):
    return NORMALIZERS.get(doc_type, normalize_invoice)


# ─── Original-file storage ───────────────────────────────────────────────────
def extraction_dir(eid: str) -> str:
    return os.path.join(Config.UPLOAD_DIR, eid)


def save_files(eid: str, pages: list[dict]) -> None:
    d = extraction_dir(eid)
    os.makedirs(d, exist_ok=True)
    for i, p in enumerate(pages):
        safe = secure_filename(p["name"]) or f"page{i}"
        with open(os.path.join(d, f"{i}__{safe}"), "wb") as fh:
            fh.write(p["bytes"])


def list_files(eid: str) -> list[dict]:
    d = extraction_dir(eid)
    if not os.path.isdir(d):
        return []
    out = []
    for fn in os.listdir(d):
        idx, sep, orig = fn.partition("__")
        if not sep or not idx.isdigit():
            continue
        mime = mimetypes.guess_type(orig)[0] or "application/octet-stream"
        out.append({"index": int(idx), "name": orig, "mime": mime})
    out.sort(key=lambda x: x["index"])
    return out


# ─── Headline fields ─────────────────────────────────────────────────────────
def apply_headline_fields(row, data: dict) -> None:
    """Denormalize headline fields for fast list rendering. Maps invoice, receipt
    and statement shapes onto the shared columns (merchant→vendor, receipt_date→date)."""
    if row.doc_type == "receipt":
        row.vendor_name = (data.get("merchant") or {}).get("name")
        row.invoice_number = data.get("receipt_number")
        row.invoice_date = data.get("receipt_date")
        row.due_date = None
        row.total = data.get("total")
    elif row.doc_type == "statement":
        row.vendor_name = data.get("account_holder") or data.get("bank_name")
        row.invoice_number = data.get("account_number")
        row.invoice_date = data.get("period_start")
        row.due_date = data.get("period_end")
        row.total = data.get("closing_balance")
    else:
        row.vendor_name = (data.get("vendor") or {}).get("name")
        row.invoice_number = data.get("invoice_number")
        row.invoice_date = data.get("invoice_date")
        row.due_date = data.get("due_date")
        row.total = data.get("total")
    row.currency = data.get("currency")
    row.data = json.dumps(data)
