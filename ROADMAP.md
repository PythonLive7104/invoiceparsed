# Roadmap

Planned features, not yet built. Captured so they're not lost.

## ✅ Receipt support — SHIPPED

Receipts are now a first-class document type alongside invoices: a type toggle on
upload, a dedicated receipt schema (merchant, date, payment method, category,
tip, totals + confidence), a `ReceiptCard`, expense-friendly CSV, and history
labelling. Implementation below kept for reference.

<details><summary>Original plan</summary>

**Why:** Today InvoiceParsed targets *invoices*. Adding *receipts* expands the
addressable market significantly — freelancers and SMBs photograph expense
receipts far more often than they handle invoices, and it fits the same
"snap → structured data → export to accounting" workflow.

**Scope (MVP):**
- Accept a "document type" of `receipt` alongside `invoice` (auto-detect, or a
  toggle on upload).
- A receipt schema: merchant, date, payment method, category (best-guess),
  line items (optional), subtotal, tax, tip, total, currency — each with a
  confidence score (mirrors the invoice schema pattern).
- QuickBooks/expense-friendly CSV export for receipts (Date, Merchant, Category,
  Amount, Tax, Total, Payment method).
- History filter by document type.

**Implementation outline (reuses existing architecture):**
1. **Backend**
   - Add `receipt_schema.py` modeled on `invoice_schema.py` (JSON schema +
     `normalize()`), and a receipt prompt in `openai_service.py` (or branch the
     existing one on document type).
   - Add a `doc_type` column to the `Extraction` model (default `"invoice"`),
     plus a migration/`ALTER TABLE` on Supabase.
   - `/api/extract` accepts `doc_type` (form field), routes to the right
     schema/prompt; `_apply_headline_fields` handles both shapes.
   - Receipt CSV in `csv_util.py` (`receipt_to_csv`).
2. **Frontend**
   - Upload toggle (Invoice / Receipt) in `ExtractWorkspace`.
   - A `ReceiptCard` result view (or generalize `InvoiceCard`).
   - History column/filter for type.
3. **Marketing/SEO**
   - New use-case + blog entries ("extract data from receipts", "receipt OCR")
     in `content/registry.js` — they auto-flow into the sitemap/prerender.

**Effort:** ~1–2 focused sessions. Largely a parallel of the invoice path, so
low architectural risk.

**Pricing angle:** could be a paid-tier differentiator, or included to drive
free-plan signups and broaden the funnel.

</details>

## Still planned

- **Receipt-specific marketing pages** — a `/use-cases/receipts` and a "receipt
  OCR" blog post in `content/registry.js` (auto-flows into sitemap + prerender).
- **QuickBooks API sync** — true one-click push (OAuth + API) instead of CSV
  import. Bigger lift; CSV covers the near term.
