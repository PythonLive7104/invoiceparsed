"""OpenAI-powered invoice extraction.

Sends an invoice (image or PDF) to a vision-capable model and returns a
validated invoice dict matching the PRD schema, using structured outputs so the
response always conforms to our JSON contract.
"""
import base64
import json

from openai import OpenAI

from config import Config
from invoice_schema import INVOICE_JSON_SCHEMA, normalize
from invoice_schema import normalize as normalize_invoice
from receipt_schema import RECEIPT_JSON_SCHEMA
from receipt_schema import normalize as normalize_receipt
from statement_schema import STATEMENT_JSON_SCHEMA
from statement_schema import normalize as normalize_statement

SYSTEM_PROMPT = """You are an expert invoice data-extraction engine for InvoiceParsed.
You receive one invoice (possibly spanning multiple pages or files) as images
and/or PDFs and return clean, structured data.

Rules:
- All provided pages/files belong to the SAME invoice. Merge them into a single
  result: combine line items across pages and use the totals from the final page.
- Extract values exactly as they appear on the document. Do not invent data.
- Normalize dates to ISO 8601 (YYYY-MM-DD) when the date is unambiguous.
- Use the ISO 4217 currency code (e.g. USD, EUR, GBP) inferred from symbols or text.
- Numeric fields (quantities, prices, amounts, subtotal, tax, total) must be plain
  numbers with no currency symbols, commas, or thousands separators.
- If a field is genuinely not present on the invoice, return null for it.
- Capture every line item you can see, in order.
- For every field, also report a confidence score from 0 to 1 in the `confidence`
  object: 1 means you are certain the value is correct and clearly legible; lower
  values mean the value was unclear, ambiguous, inferred, or not found (use a value
  near 0 for fields you returned as null)."""

RECEIPT_PROMPT = """You are an expert receipt data-extraction engine for InvoiceParsed.
You receive one receipt (possibly spanning multiple pages/photos) as images
and/or PDFs and return clean, structured data.

Rules:
- All provided pages/files belong to the SAME receipt. Merge them into one result.
- Extract values exactly as they appear. Do not invent data.
- Normalize dates to ISO 8601 (YYYY-MM-DD) when unambiguous.
- Use the ISO 4217 currency code (e.g. USD, EUR, GBP) inferred from symbols or text.
- payment_method: capture how it was paid (e.g. "Visa ****1234", "Cash", "Amex").
- category: infer a best-guess expense category (e.g. Meals, Travel, Fuel,
  Office Supplies, Groceries). Use null only if there is no reasonable guess.
- Numeric fields must be plain numbers with no symbols, commas or separators.
- tip is the gratuity if present, else null. If a field is genuinely absent, null.
- For every field, also report a confidence score from 0 to 1 in `confidence`:
  1 = certain and clearly legible; lower = unclear/inferred/not found (near 0 for
  fields returned as null)."""

STATEMENT_PROMPT = """You are an expert bank-statement data-extraction engine for InvoiceParsed.
You receive a bank/wallet account statement (possibly spanning multiple pages or
screenshots) as images and/or PDFs and return clean, structured data.

Rules:
- All provided pages/files belong to the SAME statement; merge them in order and
  combine the transaction rows across pages into one list.
- Extract the account holder, account number, bank/wallet name, the statement
  period (start and end dates), opening and closing balances, and the total debit
  and total credit if shown.
- Normalize dates to ISO 8601 (YYYY-MM-DD) when unambiguous.
- Use the ISO 4217 currency code (e.g. USD, EUR, NGN) inferred from symbols/text.
- For EACH transaction row capture: date, description, debit (money out as a
  positive number, else null), credit (money in as a positive number, else null),
  running balance after the transaction (or null), and reference (or null).
- A row is either a debit or a credit — put the amount in the correct column and
  null in the other. Numbers must be plain (no symbols, commas or separators).
- Capture every transaction row you can see, in order. Do not invent rows.
- For every top-level field report a confidence score from 0 to 1 in `confidence`
  (1 = certain/clearly legible; near 0 = unclear/inferred/not found). The
  `transactions` confidence reflects how reliably you read the rows overall."""

# Per document type: (prompt, json schema, schema name, normalizer).
_DOC_TYPES = {
    "invoice": (SYSTEM_PROMPT, INVOICE_JSON_SCHEMA, "invoice", normalize_invoice),
    "receipt": (RECEIPT_PROMPT, RECEIPT_JSON_SCHEMA, "receipt", normalize_receipt),
    "statement": (STATEMENT_PROMPT, STATEMENT_JSON_SCHEMA, "statement", normalize_statement),
}

_client = None


def _get_client() -> OpenAI:
    global _client
    if not Config.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    if _client is None:
        _client = OpenAI(api_key=Config.OPENAI_API_KEY)
    return _client


def _is_pdf(mime: str, file_name: str) -> bool:
    return mime == "application/pdf" or file_name.lower().endswith(".pdf")


def _content_part(page: dict) -> dict:
    """Build an OpenAI content part for a single page/file."""
    b64 = base64.b64encode(page["bytes"]).decode("ascii")
    if _is_pdf(page["mime"], page["name"]):
        return {
            "type": "file",
            "file": {
                "filename": page["name"],
                "file_data": f"data:application/pdf;base64,{b64}",
            },
        }
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{page['mime']};base64,{b64}", "detail": "high"},
    }


def extract_document(pages: list[dict], doc_type: str = "invoice") -> dict:
    """Run extraction on one or more pages of a single document (invoice|receipt).

    `pages` is a list of dicts: {"bytes": ..., "mime": ..., "name": ...}.
    A single-page document is just a list of length 1. Returns normalized data.
    """
    if not pages:
        raise RuntimeError("No pages provided for extraction.")
    prompt, schema, schema_name, normalizer = _DOC_TYPES.get(doc_type, _DOC_TYPES["invoice"])
    label = {"receipt": "receipt", "statement": "bank statement"}.get(doc_type, "invoice")
    model = {
        "invoice": Config.MODEL_INVOICE,
        "receipt": Config.MODEL_RECEIPT,
        "statement": Config.MODEL_STATEMENT,
    }.get(doc_type, Config.OPENAI_MODEL)

    intro = (
        f"This {label} spans {len(pages)} pages/files provided below, in order. "
        f"Extract all structured data into the required schema, merging the pages "
        "into one result."
        if len(pages) > 1
        else f"Extract all structured data from this {label} into the required schema."
    )

    user_content = [{"type": "text", "text": intro}]
    for page in pages:
        user_content.append(_content_part(page))

    completion = _get_client().chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_content},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": schema},
        },
    )

    raw = completion.choices[0].message.content
    if not raw:
        raise RuntimeError("The model returned an empty response.")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("The model returned invalid JSON.") from exc

    return normalizer(parsed)


def extract_invoice(pages: list[dict]) -> dict:
    """Back-compat wrapper for invoice extraction."""
    return extract_document(pages, "invoice")
