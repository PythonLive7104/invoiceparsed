// Content registry — the single source of truth for marketing routes.
// Both the React pages and the build-time sitemap/prerender import this, so
// adding an entry here automatically adds it to the sitemap and gets prerendered.
//
// `content` is an array of blocks rendered both by React (ArticleBody) and by the
// prerenderer (injected into static HTML for crawlers/AEO). Block shapes:
//   { h2: "Heading" } | { p: "paragraph" } | { ul: ["item", ...] } | { ol: [...] }
//
// Pure JS (no JSX/aliases) so scripts/*.mjs can import it.

// Static, always-present routes. `changefreq`/`priority` feed the sitemap.
export const STATIC_ROUTES = [
  { path: "/", changefreq: "weekly", priority: 1.0 },
  { path: "/pricing", changefreq: "monthly", priority: 0.9 },
  { path: "/faq", changefreq: "monthly", priority: 0.7 },
  { path: "/about", changefreq: "yearly", priority: 0.5 },
  { path: "/contact", changefreq: "yearly", priority: 0.5 },
  { path: "/docs", changefreq: "monthly", priority: 0.7 },
  { path: "/blog", changefreq: "weekly", priority: 0.7 },
  { path: "/compare", changefreq: "monthly", priority: 0.6 },
  { path: "/use-cases", changefreq: "monthly", priority: 0.6 },
];

export const BLOG_POSTS = [
  {
    slug: "extract-data-from-invoice-pdf",
    title: "How to Extract Data From an Invoice PDF (2026 Guide)",
    description:
      "Learn how to extract data from invoice PDFs automatically with AI — no manual data entry, no templates. Get clean JSON or CSV in seconds.",
    excerpt:
      "To extract data from an invoice PDF, upload it to an AI invoice parser like InvoiceParsed, which reads the document and returns structured fields (vendor, line items, totals, tax) as JSON or CSV in seconds — no templates or manual entry required.",
    author: "InvoiceParsed Team",
    datePublished: "2026-01-15",
    dateModified: "2026-06-08",
    image: "/og/blog/extract-invoice-pdf.png",
    tags: ["invoice extraction", "PDF", "automation"],
    content: [
      { h2: "What does 'extract data from an invoice PDF' mean?" },
      { p: "Extracting data from an invoice PDF means turning the document — whether it's a digital PDF or a scanned image — into structured, machine-readable fields you can use in a spreadsheet, accounting tool, or database. Instead of a flat file a human has to read, you get labelled values: vendor name, invoice number, dates, line items, tax and total." },
      { p: "The hard part has always been that every supplier formats invoices differently. Older tools needed a custom template per vendor. Modern AI invoice parsers understand layout and context, so they work across formats without any template setup." },
      { h2: "The fastest method: an AI invoice parser" },
      { p: "The quickest, most accurate way to extract invoice data in 2026 is to use an AI parser. The workflow is three steps:" },
      { ol: [
        "Upload the invoice PDF (or a photo/scan).",
        "The AI reads the document and maps every field into a structured schema.",
        "Review the result and export it as JSON or a QuickBooks-compatible CSV — or pull it via API.",
      ] },
      { p: "With InvoiceParsed this takes a few seconds per document, and every field comes back with a confidence score so you know which values to double-check." },
      { h2: "What fields can be extracted?" },
      { ul: [
        "Vendor details — name, address, email",
        "Invoice number and invoice/due dates",
        "Currency and payment terms",
        "Line items — description, quantity, unit price, amount",
        "Subtotal, tax and total",
      ] },
      { h2: "Other ways to extract invoice data (and their trade-offs)" },
      { p: "Manual data entry is accurate for one-offs but slow and error-prone at volume — typically 2–5 minutes per invoice. Traditional OCR returns raw text you still have to parse and label yourself. Template-based tools work well for a single fixed layout but break the moment a vendor changes their format. AI extraction avoids all three problems, which is why it has become the default for small teams." },
      { h2: "How to keep accuracy high" },
      { ul: [
        "Upload the highest-resolution copy you have — clear scans beat blurry photos.",
        "Keep multi-page invoices together so totals reconcile across pages.",
        "Use the per-field confidence scores to spot anything that needs a quick human check.",
      ] },
      { h2: "Exporting to your accounting software" },
      { p: "Once extracted, InvoiceParsed exports a CSV with QuickBooks bill/invoice column names (Bill No, Bill Date, Due Date, Terms, Description, Qty, Rate, Amount, Tax, Total) so it maps cleanly in the QuickBooks import wizard. You can also export JSON or push data straight into your stack via the REST API and webhooks." },
      { h2: "Get started" },
      { p: "You can extract your first invoice free — the free plan includes 5 invoices per month with no credit card required. Upload a PDF and you'll have clean, structured data in seconds." },
    ],
    faqs: [
      { q: "Can I extract data from a scanned invoice PDF?", a: "Yes. InvoiceParsed uses AI vision models that read both digital and scanned (image-based) invoice PDFs, so handwritten-style scans and photos work too." },
      { q: "What fields can be extracted from an invoice?", a: "Vendor name and address, invoice number, invoice and due dates, currency, line items (description, quantity, unit price, amount), subtotal, tax, and total — each with a confidence score." },
      { q: "Is there a free way to parse invoice PDFs online?", a: "Yes. InvoiceParsed's free plan lets you parse up to 5 invoices per month online with no credit card required." },
    ],
  },
  {
    slug: "extract-data-from-receipts",
    title: "How to Extract Data From Receipts (2026 Guide)",
    description:
      "Learn how to extract data from receipts automatically with AI — turn photos and PDFs into structured expense data (merchant, date, tax, tip, total) in seconds.",
    excerpt:
      "To extract data from a receipt, upload a photo or PDF to an AI receipt parser like InvoiceParsed, which reads the document and returns structured fields — merchant, date, payment method, category, tax, tip and total — as JSON or a QuickBooks-compatible CSV in seconds.",
    author: "InvoiceParsed Team",
    datePublished: "2026-06-08",
    dateModified: "2026-06-08",
    image: "/og/blog/extract-invoice-pdf.png",
    tags: ["receipt OCR", "expenses", "automation"],
    content: [
      { h2: "Why extract data from receipts?" },
      { p: "Receipts pile up fast — meals, fuel, supplies, travel. Manually typing each one into a spreadsheet for expenses, reimbursements or tax time is tedious and easy to get wrong. Extracting the data automatically turns a shoebox of receipts into clean, exportable records in minutes." },
      { h2: "The fastest method: snap and upload" },
      { ol: [
        "Take a photo of the receipt or upload a PDF.",
        "The AI reads it and pulls out the structured fields.",
        "Review and export to a QuickBooks-compatible CSV, JSON, or your accounting tool.",
      ] },
      { p: "InvoiceParsed handles crumpled phone photos and scans, not just clean PDFs, and returns a confidence score on every field." },
      { h2: "What gets captured from a receipt" },
      { ul: [
        "Merchant name and address",
        "Date and (where present) receipt number",
        "Payment method — e.g. Visa ****1234, cash, Amex",
        "A best-guess expense category — Meals, Travel, Fuel, Office Supplies…",
        "Line items, subtotal, tax, tip and total",
      ] },
      { h2: "Receipts vs invoices: what's different" },
      { p: "Receipts and invoices look similar but serve different purposes. Invoices are a request for payment with terms and due dates; receipts are proof of a completed purchase, often with a tip and a payment method. InvoiceParsed has a dedicated receipt mode so the fields match what actually appears on a receipt — including tip and expense category — rather than forcing it into an invoice shape." },
      { h2: "Tips for clean expense data" },
      { ul: [
        "Photograph receipts flat and in good light to maximise accuracy.",
        "Capture the whole receipt, including the totals at the bottom.",
        "Let the AI suggest a category, then adjust if needed before export.",
      ] },
      { h2: "Export for expenses and accounting" },
      { p: "InvoiceParsed exports receipts as an expense-friendly CSV (Merchant, Date, Payment Method, Category, Tax, Tip, Total) that imports into QuickBooks and most accounting tools, or as JSON via the API for automated workflows." },
      { h2: "Try it free" },
      { p: "The free plan covers 5 documents per month — invoices or receipts — with no credit card required. Snap a receipt and see the structured data in seconds." },
    ],
    faqs: [
      { q: "What is receipt OCR?", a: "Receipt OCR converts the text on a receipt image or PDF into machine-readable data. AI receipt parsers go further, labelling that text into structured fields like merchant, tax, tip and total." },
      { q: "Can AI categorize receipts for expenses?", a: "Yes. InvoiceParsed infers a best-guess expense category (e.g. Meals, Travel, Fuel) for each receipt, which you can review and export." },
    ],
  },
  {
    slug: "best-invoice-ocr-tools",
    title: "7 Best Invoice OCR Tools in 2026 (Compared)",
    description:
      "A practical comparison of the best invoice OCR tools in 2026 for freelancers and small businesses — accuracy, pricing, API access and export formats.",
    excerpt:
      "The best invoice OCR tools in 2026 combine AI extraction with structured export. For freelancers and small teams, InvoiceParsed offers the fastest setup and per-field confidence scores; alternatives suit higher-volume enterprise workflows.",
    author: "InvoiceParsed Team",
    datePublished: "2026-02-03",
    dateModified: "2026-06-08",
    image: "/og/blog/invoice-ocr-tools.png",
    tags: ["invoice OCR", "comparison", "tools"],
    content: [
      { h2: "What to look for in an invoice OCR tool" },
      { p: "Not all 'OCR' is equal. Plain OCR just reads text off the page; what you actually want is structured extraction that labels the vendor, line items, tax and total. When comparing tools in 2026, weigh these factors:" },
      { ul: [
        "Accuracy across varied layouts (no per-vendor templates)",
        "Structured export — JSON and accounting-ready CSV",
        "Per-field confidence so you know what to review",
        "API and webhooks for automation",
        "Pricing that fits your volume, with a real free tier",
      ] },
      { h2: "The shortlist" },
      { p: "Below is a practical look at categories of tools and who each suits. Pricing and features change often, so verify current details before committing." },
      { h2: "1. InvoiceParsed — best for freelancers and small teams" },
      { p: "AI extraction with no templates, per-field confidence scores, invoice and receipt support, QuickBooks-compatible CSV, plus a REST API and webhooks on paid plans. Starts free (5/month). Designed to be set up in minutes." },
      { h2: "2. Enterprise IDP platforms" },
      { p: "Document-processing suites aimed at large finance teams offer deep workflow and ERP integrations, but come with enterprise pricing and onboarding. Overkill for most freelancers and SMBs." },
      { h2: "3. General-purpose OCR APIs" },
      { p: "Raw OCR services return text and bounding boxes cheaply, but you have to build the logic to turn that text into invoice fields yourself — extra engineering most small teams don't want." },
      { h2: "4. Accounting-suite capture add-ons" },
      { p: "Some accounting platforms bundle receipt/invoice capture. Convenient if you're locked into that suite, but typically weaker on API access and multi-format export." },
      { h2: "5–7. Niche and regional tools" },
      { p: "A range of niche tools focus on specific regions, languages or document types. They can be a good fit if you have a narrow, consistent use case, but tend to lack the flexibility of AI extraction across arbitrary layouts." },
      { h2: "How to choose" },
      { ul: [
        "Solo or small team, want it working today → an AI parser with a free tier.",
        "Developer automating a pipeline → prioritise API + webhooks + JSON schema.",
        "Large enterprise with ERP needs → evaluate an IDP platform.",
      ] },
      { h2: "Bottom line" },
      { p: "For most freelancers and small businesses, an AI invoice parser like InvoiceParsed gives the best balance of accuracy, speed and price — with no templates to maintain. Try it free and compare the output against your current process." },
    ],
    faqs: [
      { q: "What is invoice OCR?", a: "Invoice OCR (Optical Character Recognition) converts the text in an invoice image or PDF into machine-readable data. Modern AI tools go further, mapping that text into structured fields like totals and line items." },
      { q: "Is AI invoice extraction more accurate than traditional OCR?", a: "Generally yes. Traditional OCR returns raw text; AI invoice parsers understand layout and context, so they correctly label vendors, dates and line items even across varied invoice formats." },
    ],
  },
];

export const COMPARISONS = [
  {
    slug: "invoiceparsed-vs-manual-data-entry",
    title: "InvoiceParsed vs Manual Data Entry",
    description:
      "InvoiceParsed vs manual data entry: compare speed, accuracy and cost of AI invoice extraction against typing invoice data by hand.",
    excerpt:
      "InvoiceParsed extracts invoice data in seconds with per-field confidence scores, while manual data entry averages several minutes per invoice and is error-prone — automation wins on speed, accuracy and cost at any meaningful volume.",
    dateModified: "2026-06-08",
    content: [
      { h2: "The short answer" },
      { p: "If you process more than a handful of invoices a month, AI extraction beats manual data entry on every axis that matters: speed, accuracy and cost. Manual entry only makes sense for very low volumes or unusual one-off documents." },
      { h2: "Speed" },
      { p: "Typing an invoice into a spreadsheet or accounting tool takes roughly 2–5 minutes once you account for reading, transcribing and double-checking. InvoiceParsed returns structured data in a few seconds — a 20–50x speedup before you factor in error correction." },
      { h2: "Accuracy" },
      { p: "Manual entry introduces transposition errors, missed line items and wrong totals, especially late in the day or at volume. AI extraction is consistent and surfaces a confidence score per field, so you review the few uncertain values instead of re-checking everything." },
      { h2: "Cost" },
      { p: "Manual entry costs labour hours that scale linearly with volume. AI extraction is a flat, predictable subscription — and the free tier covers low volumes entirely. As you grow, the cost per invoice keeps falling rather than rising." },
      { h2: "When manual entry still makes sense" },
      { ul: [
        "You handle only one or two invoices a month.",
        "A document is so unusual or damaged that a human read is genuinely required.",
        "You need to capture something not on the document at all.",
      ] },
      { h2: "The verdict" },
      { p: "For freelancers and small businesses, AI extraction removes the most tedious part of bookkeeping while improving accuracy. Start free with InvoiceParsed and compare it directly against your current manual process on your next batch of invoices." },
    ],
    faqs: [
      { q: "How much faster is AI invoice extraction than manual entry?", a: "AI extraction typically processes an invoice in a few seconds versus 2–5 minutes of manual typing, a 20–50x speedup before accounting for error correction." },
    ],
  },
  {
    slug: "invoiceparsed-vs-traditional-ocr",
    title: "InvoiceParsed vs Traditional OCR Software",
    description:
      "InvoiceParsed vs traditional OCR: see why AI invoice parsing returns structured fields instead of raw text, with less setup and no templates.",
    excerpt:
      "Traditional OCR returns unstructured text you still have to parse, while InvoiceParsed returns labelled, structured invoice fields directly — removing template setup and post-processing for most small-business workflows.",
    dateModified: "2026-06-08",
    content: [
      { h2: "Raw text vs structured data" },
      { p: "Traditional OCR converts an image into text. That's useful, but an invoice's meaning lives in its structure — which number is the total, which lines are items, which date is the due date. With plain OCR you still have to write rules or templates to turn the text into fields. AI parsing returns the structured fields directly." },
      { h2: "Templates vs understanding" },
      { p: "Classic OCR pipelines rely on per-vendor templates that map fixed positions to fields. They work until a supplier changes their layout — then they silently break. InvoiceParsed uses AI that understands invoice structure, so it generalises across formats with no templates to build or maintain." },
      { h2: "Post-processing effort" },
      { ul: [
        "Traditional OCR: read text → write parsing logic → handle every layout edge case → validate.",
        "InvoiceParsed: upload → receive validated, structured JSON/CSV with confidence scores.",
      ] },
      { h2: "Accuracy and confidence" },
      { p: "Because the AI reasons about context, it correctly distinguishes a subtotal from a total or a quantity from a unit price even when labels are missing or unusual. Each field includes a confidence score so you can target review where it's needed." },
      { h2: "When traditional OCR fits" },
      { p: "If you only need raw text from documents (not structured invoice fields), or you're building a fully custom pipeline and want the cheapest possible text layer, a general OCR engine is fine. For turning invoices into usable accounting data, AI extraction is far less work." },
      { h2: "The verdict" },
      { p: "For invoice and receipt workflows, InvoiceParsed removes the parsing and template burden that traditional OCR leaves on you. Try it free and compare the output to your current OCR step." },
    ],
    faqs: [
      { q: "Does InvoiceParsed require templates like older OCR tools?", a: "No. InvoiceParsed uses AI that understands invoice layouts, so it works across formats without per-vendor templates." },
    ],
  },
];

export const USE_CASES = [
  {
    slug: "freelancers",
    title: "Invoice Data Extraction for Freelancers",
    description:
      "Automate invoice data entry as a freelancer. Upload client invoices and receipts, get clean structured data for bookkeeping and taxes in seconds.",
    excerpt:
      "Freelancers use InvoiceParsed to turn client invoices and receipts into structured data for bookkeeping and tax time — upload a PDF or photo and export clean JSON or CSV without manual typing.",
    dateModified: "2026-06-08",
    content: [
      { h2: "The freelancer bookkeeping problem" },
      { p: "As a freelancer you wear every hat, and bookkeeping is the one nobody enjoys. Client invoices, software receipts and expense slips arrive in every format imaginable, and logging them by hand eats hours you could bill." },
      { h2: "How InvoiceParsed helps" },
      { ul: [
        "Drag in a client invoice or snap a receipt — get structured data in seconds.",
        "Export a QuickBooks-compatible CSV for your books, or JSON if you're technical.",
        "Keep a searchable history of everything you've processed for tax time.",
      ] },
      { h2: "A simple monthly workflow" },
      { ol: [
        "Collect the month's invoices and receipts in one folder.",
        "Upload them (the free plan covers 5/month; paid plans add batch upload).",
        "Skim the confidence scores, fix anything flagged, and export to CSV.",
        "Hand the CSV to your accountant or import it into your accounting tool.",
      ] },
      { h2: "Why freelancers choose it" },
      { p: "No templates, no setup, and a free tier that's genuinely enough for many solo freelancers. When your client load grows, batch upload and the API are there without changing your workflow." },
      { h2: "Start free" },
      { p: "Process your first 5 documents a month free, no card required. Reclaim the hours you currently spend retyping numbers." },
    ],
    faqs: [
      { q: "Can freelancers use InvoiceParsed for free?", a: "Yes. The free plan covers 5 invoices per month, which is enough for many solo freelancers to handle monthly bookkeeping." },
    ],
  },
  {
    slug: "receipts",
    title: "Receipt Data Extraction & OCR",
    description:
      "Extract data from receipts automatically with AI. Snap a photo or upload a PDF and get merchant, date, tax, tip and total as JSON or CSV for expenses.",
    excerpt:
      "InvoiceParsed extracts data from receipts using AI — upload a photo or PDF and it returns the merchant, date, payment method, category, tax, tip and total as structured data you can export to a QuickBooks-compatible CSV. Ideal for expense tracking and reimbursements.",
    dateModified: "2026-06-08",
    content: [
      { h2: "Turn receipts into expense data" },
      { p: "Receipt data extraction converts a photo or PDF of a receipt into structured fields — merchant, date, payment method, category, tax, tip and total — ready for expense reports, reimbursements and tax records." },
      { h2: "Built for real receipts" },
      { p: "InvoiceParsed reads phone photos and scans, not just clean PDFs, and uses a dedicated receipt schema so the captured fields match what's actually on a receipt, including tip and a best-guess expense category." },
      { h2: "What you get" },
      { ul: [
        "Merchant, date and payment method",
        "Auto-suggested expense category (Meals, Travel, Fuel, …)",
        "Line items, subtotal, tax, tip and total — each with a confidence score",
        "Expense/QuickBooks-friendly CSV and JSON export",
      ] },
      { h2: "Who it's for" },
      { p: "Freelancers tracking deductible expenses, employees filing reimbursements, and small finance teams processing supplier receipts at volume. Switch the document type to 'Receipt' on upload and the rest of the workflow is identical to invoices." },
      { h2: "Start free" },
      { p: "The free plan includes 5 documents per month — invoices or receipts — with no credit card required." },
    ],
    faqs: [
      { q: "Can I extract data from a photo of a receipt?", a: "Yes. InvoiceParsed reads phone photos of receipts as well as scans and PDFs, returning structured fields with a confidence score on each." },
      { q: "What does receipt extraction capture?", a: "Merchant name and address, date, payment method, a best-guess expense category, line items, subtotal, tax, tip and total — exported as JSON or an expense/QuickBooks-friendly CSV." },
      { q: "Is receipt scanning free?", a: "Yes — the free plan includes 5 documents per month (invoices or receipts) with no credit card required." },
    ],
  },
  {
    slug: "bank-statement-extraction",
    title: "Bank Statement Data Extraction & Conversion",
    description:
      "Convert bank statement PDFs and screenshots to structured transaction data with AI. Extract every row — date, description, debit, credit, balance — to CSV.",
    excerpt:
      "InvoiceParsed converts bank and wallet statements (PDF or screenshot) into structured transaction data — date, description, debit, credit and running balance for every row — plus account details and totals, exported to a clean CSV for accounting, bookkeeping or loan applications.",
    dateModified: "2026-06-09",
    content: [
      { h2: "Turn a statement into a transactions spreadsheet" },
      { p: "Bank statement extraction reads an account statement — a PDF or even a phone screenshot — and returns structured data: the account holder, account number, statement period, opening and closing balances, totals, and every transaction row with its date, description, debit, credit and running balance." },
      { h2: "Why it's hard by hand (and easy with AI)" },
      { p: "Statements come in endless layouts, and a single month can hold hundreds of rows. Re-typing them for bookkeeping, expense analysis, or a loan/visa application is painful and error-prone. InvoiceParsed reads the whole statement in one pass and gives you a clean table you can export." },
      { h2: "What gets captured" },
      { ul: [
        "Account holder, account number and bank/wallet name",
        "Statement period, opening & closing balance, total debit & credit",
        "Every transaction: date, description, debit, credit, running balance, reference",
        "A confidence score so you can spot rows worth a quick check",
      ] },
      { h2: "Works on screenshots too" },
      { p: "Mobile banking and wallet apps (e.g. OPay, Kuda, Cash App) often only give you a screenshot or a flat PDF. InvoiceParsed handles those directly — no need for a special export format." },
      { h2: "Export for accounting & analysis" },
      { p: "Download the transactions as a CSV (date, description, debit, credit, balance, reference) ready for Excel, Google Sheets or your accounting tool, or pull the structured JSON via the API." },
      { h2: "Common uses" },
      { ul: [
        "Bookkeeping and reconciliation",
        "Expense and cash-flow analysis",
        "Loan, mortgage or visa applications that require statement data",
        "Migrating historical transactions into accounting software",
      ] },
      { h2: "Try it free" },
      { p: "Pick \"Statement\" on upload and process your first one on the free plan (5 documents/month, no card). You'll get a structured transactions table in seconds." },
    ],
    faqs: [
      { q: "Can it extract data from a bank statement screenshot?", a: "Yes. InvoiceParsed reads statement screenshots and photos as well as PDFs, returning every transaction row as structured data." },
      { q: "What's included in the export?", a: "A CSV (or JSON) with each transaction's date, description, debit, credit, running balance and reference, plus account details and totals." },
      { q: "Does it handle wallet apps like OPay or Cash App?", a: "Yes — any bank or wallet account statement works, including the screenshot-style statements those apps produce." },
    ],
  },
  {
    slug: "small-business-accounting",
    title: "Invoice Extraction for Small Business Accounting",
    description:
      "Speed up small business accounting with automated invoice data extraction. Export to CSV or push to your accounting stack via the API.",
    excerpt:
      "Small businesses use InvoiceParsed to automate accounts-payable data entry — batch-upload supplier invoices, extract structured fields, and export to CSV or feed your accounting software through the REST API.",
    dateModified: "2026-06-08",
    content: [
      { h2: "Accounts payable without the data entry" },
      { p: "For a small business, accounts payable means a steady stream of supplier invoices that someone has to key into the books. InvoiceParsed automates that step: upload the invoices, get structured data, and move straight to review and payment." },
      { h2: "Built for volume" },
      { ul: [
        "Batch upload many invoices at once (paid plans), processed with live per-file status.",
        "Multi-page invoices combined into a single record.",
        "Consistent, structured output with per-field confidence for fast review.",
      ] },
      { h2: "Fits your accounting stack" },
      { p: "Export a QuickBooks-compatible CSV that maps cleanly in the import wizard, or connect the REST API and webhooks to push extracted invoices straight into your accounting or ERP system as they're processed." },
      { h2: "A typical AP workflow" },
      { ol: [
        "Forward or upload supplier invoices as they arrive.",
        "Batch-extract them into structured records.",
        "Review flagged fields, then export or sync to your accounting tool.",
        "Keep the searchable history for audits and month-end.",
      ] },
      { h2: "Scale when you're ready" },
      { p: "Start on a plan that matches your monthly volume and move up as you grow — the Pro and Business plans add unlimited processing, API access and webhooks. Try it free to see the time saved on your next batch of invoices." },
    ],
    faqs: [
      { q: "Can I connect InvoiceParsed to my accounting software?", a: "Yes. On the Pro plan you can use the REST API and webhooks to push extracted invoice data into your accounting or ERP system automatically." },
    ],
  },
];

// FAQ shown on /pricing (also rendered as FAQPage JSON-LD).
export const PRICING_FAQS = [
  { q: "Is there a free plan?", a: "Yes. The Free plan includes 5 invoices per month with no credit card required — enough for many solo freelancers." },
  { q: "Can I change plans later?", a: "Yes, you can upgrade or downgrade at any time from your dashboard; changes take effect immediately." },
  { q: "What counts as one invoice?", a: "Each completed extraction counts as one invoice against your monthly limit. A multi-page PDF processed as a single invoice counts once." },
  { q: "Do you offer an API?", a: "Yes. REST API access and webhooks are included on the Pro and Business plans for automating invoice processing." },
];

// Site-wide FAQ shown on / and /faq (also rendered as FAQPage JSON-LD).
export const SITE_FAQS = [
  { q: "What is InvoiceParsed?", a: "InvoiceParsed is an AI-powered tool that extracts data from invoices, receipts and bank statements. Upload a PDF or image and it returns structured data — vendor, line items, tax and totals — as Excel, CSV or JSON in seconds." },
  { q: "How accurate is AI invoice extraction?", a: "InvoiceParsed returns a confidence score (0–100%) for every field, so you can review low-confidence values. Accuracy is highest on clear digital PDFs and remains strong on photos and scans." },
  { q: "Which file formats are supported?", a: "PDF, JPG and PNG files up to 10MB each. Multi-page PDFs and multi-file documents are supported on paid plans." },
  { q: "Is there a free plan?", a: "Yes — the free plan includes 5 documents per month with no credit card required." },
  { q: "What export formats are supported?", a: "Every extraction exports as an Excel (.xlsx) workbook, a QuickBooks-compatible CSV (bill/invoice columns like Bill No, Bill Date, Terms, line items, tax and total that map cleanly in QuickBooks' CSV import), or structured JSON — and you can also pull data via the REST API." },
  { q: "Does InvoiceParsed work with bank statements from any bank?", a: "Yes. InvoiceParsed reads bank statements using AI rather than per-bank templates, so it handles different layouts from any bank. Bank statement extraction is available on the Business plan, which includes 200 statements per month." },
  { q: "What happens to my documents after processing?", a: "Your documents are processed solely to extract the data you request. They are never used to train AI models and are never sold or shared with third parties." },
  { q: "Does InvoiceParsed have an API?", a: "Yes. A REST API and webhooks are included on the Pro and Business plans — POST a PDF or image to /api/extract and get structured JSON back, ideal for automating invoice processing in your own apps." },
  { q: "Does it support multiple currencies?", a: "Yes. InvoiceParsed detects and preserves the currency on each document, so invoices and receipts in USD, EUR, GBP and other currencies are extracted accurately with the correct currency code." },
];

/** Build the full list of sitemap entries from the registry. */
export function allRoutes() {
  const dynamic = [
    ...BLOG_POSTS.map((p) => ({ path: `/blog/${p.slug}`, changefreq: "monthly", priority: 0.6, lastmod: p.dateModified })),
    ...COMPARISONS.map((c) => ({ path: `/compare/${c.slug}`, changefreq: "monthly", priority: 0.6, lastmod: c.dateModified })),
    ...USE_CASES.map((u) => ({ path: `/use-cases/${u.slug}`, changefreq: "monthly", priority: 0.6, lastmod: u.dateModified })),
  ];
  return [...STATIC_ROUTES, ...dynamic];
}
