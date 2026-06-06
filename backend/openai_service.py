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


def extract_invoice(pages: list[dict]) -> dict:
    """Run extraction on one or more pages of a single invoice.

    `pages` is a list of dicts: {"bytes": ..., "mime": ..., "name": ...}.
    A single-page invoice is just a list of length 1. Returns a normalized invoice.
    """
    if not pages:
        raise RuntimeError("No pages provided for extraction.")

    intro = (
        f"This invoice spans {len(pages)} pages/files provided below, in order. "
        "Extract all structured data into the required schema, merging the pages "
        "into one result."
        if len(pages) > 1
        else "Extract all structured data from this invoice into the required schema."
    )

    user_content = [{"type": "text", "text": intro}]
    for page in pages:
        user_content.append(_content_part(page))

    completion = _get_client().chat.completions.create(
        model=Config.OPENAI_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "invoice",
                "strict": True,
                "schema": INVOICE_JSON_SCHEMA,
            },
        },
    )

    raw = completion.choices[0].message.content
    if not raw:
        raise RuntimeError("The model returned an empty response.")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("The model returned invalid JSON.") from exc

    return normalize(parsed)
