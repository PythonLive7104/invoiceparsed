"""Local, rule-based support assistant — answers from project knowledge, no AI
calls. Matches a user's message against keyword intents and returns the best
canned answer (with a helpful fallback that points to the contact form)."""

# Each intent: trigger keywords (substring match, lowercased) + the answer.
# Order matters only for ties; scoring picks the most-matched intent.
KB = [
    {
        "id": "greeting",
        "keywords": ["hello", "hi ", "hey", "good morning", "good afternoon", "good evening", "howdy"],
        "answer": "Hi! 👋 I'm the InvoiceParsed assistant. Ask me about features, pricing, supported files, exports, or how it works.",
    },
    {
        "id": "what",
        "keywords": ["what is", "what's invoiceparsed", "what does", "about", "purpose", "overview"],
        "answer": "InvoiceParsed is an AI tool that extracts data from invoices, receipts and bank statements. Upload a PDF or image and get clean structured data — vendor, line items, tax, totals — back in seconds, with a confidence score on every field.",
    },
    {
        "id": "pricing",
        "keywords": ["price", "pricing", "cost", "how much", "plan", "subscription", "tier", "expensive"],
        "answer": "Plans (per month): Free $0 (5 documents), Starter $19 (100 docs + batch & multi-page), Pro $49 (unlimited docs + REST API & webhooks), Business $99 (everything in Pro plus bank statement extraction). The free plan needs no credit card. See /pricing for details.",
    },
    {
        "id": "free",
        "keywords": ["free", "trial", "credit card", "free plan", "try"],
        "answer": "Yes — the Free plan includes 5 documents per month with no credit card required. Just sign up, confirm your email, and start extracting.",
    },
    {
        "id": "formats",
        "keywords": ["format", "file type", "pdf", "jpg", "jpeg", "png", "image", "photo", "scan", "size", "upload"],
        "answer": "You can upload PDF, JPG or PNG files up to 10MB each. Scans and phone photos work too, not just digital PDFs.",
    },
    {
        "id": "exports",
        "keywords": ["export", "csv", "excel", "xlsx", "json", "quickbooks", "spreadsheet", "download", "accounting"],
        "answer": "Every extraction exports as Excel (.xlsx), a QuickBooks-compatible CSV, or JSON. Pro and Business plans also offer a REST API and webhooks to push data into your stack automatically.",
    },
    {
        "id": "receipts",
        "keywords": ["receipt"],
        "answer": "Yes — switch the document type to 'Receipt' and upload a photo or PDF. You'll get merchant, date, payment method, a best-guess expense category, tip and totals, exported to Excel/CSV/JSON.",
    },
    {
        "id": "statements",
        "keywords": ["bank statement", "statement", "transactions", "opay", "wallet"],
        "answer": "Bank statement extraction turns a statement (PDF or screenshot) into a clean transactions table — date, description, debit, credit, balance — plus account details and totals. It's available on the Business plan.",
    },
    {
        "id": "invoice",
        "keywords": ["invoice"],
        "answer": "Upload an invoice (PDF or image) and InvoiceParsed extracts the vendor, invoice number, dates, line items, subtotal, tax and total — each with a confidence score — ready to export to Excel, CSV or JSON.",
    },
    {
        "id": "api",
        "keywords": ["api", "webhook", "integrat", "developer", "automate", "endpoint"],
        "answer": "REST API access and webhooks are included on the Pro and Business plans. Create an API key in your dashboard and POST documents programmatically; webhooks fire when an extraction completes. See the API section on the homepage.",
    },
    {
        "id": "accuracy",
        "keywords": ["accurate", "accuracy", "confidence", "reliable", "quality", "correct"],
        "answer": "Every field comes back with a 0–100% confidence score so you can quickly review anything uncertain. Accuracy is highest on clear PDFs and remains strong on photos and scans.",
    },
    {
        "id": "multipage",
        "keywords": ["multi-page", "multi page", "multiple pages", "batch", "many files", "bulk"],
        "answer": "A single multi-page PDF works on any plan. Combining several separate files into one document, or batch-processing many files at once, is available on paid plans (Starter and up).",
    },
    {
        "id": "security",
        "keywords": ["secure", "security", "privacy", "safe", "gdpr", "data", "store", "training"],
        "answer": "Your documents are processed only to extract data — they're never used for training or resold. Access is protected by authenticated sessions and per-account isolation.",
    },
    {
        "id": "how",
        "keywords": ["how do", "how does", "how to", "get started", "start", "use it", "steps", "work"],
        "answer": "Three steps: 1) Sign up free and confirm your email, 2) choose the document type and upload a PDF or image, 3) review the result and export to Excel, CSV or JSON. It takes seconds.",
    },
    {
        "id": "contact",
        "keywords": ["contact", "support", "help", "email", "reach", "talk to", "human", "refund", "cancel", "billing", "account"],
        "answer": "For account-specific help (billing, refunds, a specific extraction), use the contact form at /contact or email invoiceparsed@gmail.com — we'll get back to you.",
    },
]

FALLBACK = (
    "I'm not sure about that one. I can help with features, pricing, supported "
    "files, exports, the API, or how it works. For anything account-specific, "
    "use the contact form at /contact or email invoiceparsed@gmail.com."
)


def answer(message: str) -> dict:
    """Return {'reply': str, 'intent': str} for a user message."""
    text = (message or "").lower()
    if not text.strip():
        return {"reply": KB[0]["answer"], "intent": "greeting"}

    best, best_score = None, 0
    for intent in KB:
        score = sum(1 for kw in intent["keywords"] if kw in text)
        if score > best_score:
            best, best_score = intent, score

    if best and best_score > 0:
        return {"reply": best["answer"], "intent": best["id"]}
    return {"reply": FALLBACK, "intent": "fallback"}
