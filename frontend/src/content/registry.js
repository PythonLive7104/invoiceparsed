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
    image: "/og/blog/extract-data-from-invoice-pdf.png",
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
    image: "/og/blog/extract-data-from-receipts.png",
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
    image: "/og/blog/best-invoice-ocr-tools.png",
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
  {
    slug: "convert-bank-statement-pdf-to-csv",
    title: "How to Convert a Bank Statement PDF to CSV (2026 Guide)",
    description:
      "Convert bank statement PDFs to clean CSV or Excel automatically with AI. Turn transactions into structured rows (date, description, amount, balance) in seconds — no manual typing.",
    excerpt:
      "To convert a bank statement PDF to CSV, upload it to an AI parser like InvoiceParsed, which reads every transaction and returns structured rows — date, description, debit, credit and running balance — ready to download as CSV or Excel in seconds, no manual typing or templates required.",
    author: "InvoiceParsed Team",
    datePublished: "2026-06-17",
    dateModified: "2026-06-17",
    image: "/og/blog/convert-bank-statement-pdf-to-csv.png",
    tags: ["bank statement", "CSV", "automation"],
    content: [
      { h2: "Why convert a bank statement PDF to CSV?" },
      { p: "Banks hand you statements as PDFs, but bookkeeping, reconciliation and tax prep all need a spreadsheet. Retyping dozens or hundreds of transactions by hand is slow and error-prone — and a single mistyped figure throws off your reconciliation. Converting the PDF to CSV gives you clean, sortable rows you can import straight into Excel, Google Sheets, QuickBooks or Xero." },
      { h2: "The fastest method: an AI parser" },
      { p: "The quickest, most reliable way in 2026 is to let an AI parser read the statement for you. The workflow is three steps:" },
      { ol: [
        "Upload the bank statement PDF (digital export or a scan).",
        "The AI reads every transaction row and maps it into structured columns.",
        "Review and download as CSV or Excel — or pull it via API.",
      ] },
      { p: "InvoiceParsed handles multi-page statements and keeps the running balance aligned, so totals reconcile against the closing balance on the statement." },
      { h2: "What columns you get" },
      { ul: [
        "Transaction date",
        "Description / payee",
        "Debit (money out) and credit (money in)",
        "Running balance",
        "Reference or transaction ID where present",
      ] },
      { h2: "Why not copy-paste or generic converters?" },
      { p: "Copy-pasting from a PDF usually collapses columns into a jumbled single line, because PDFs store text by position, not by table. Generic 'PDF to CSV' converters work on simple grids but break on real bank layouts — wrapped descriptions, multi-line transactions, and per-page subtotals. An AI parser understands the statement as a ledger, so it keeps each transaction on one row even when the description wraps." },
      { h2: "Tips for a clean export" },
      { ul: [
        "Use the bank's official PDF export rather than a screenshot when you can.",
        "Upload all pages together so the closing balance reconciles.",
        "Spot-check the first and last few rows against the statement totals before importing.",
      ] },
      { h2: "Import into your accounting tool" },
      { p: "Once you have the CSV, you can import it into Excel or Google Sheets directly, or map the columns in the QuickBooks/Xero bank import wizard. For automated workflows, InvoiceParsed can return the same data as JSON via its REST API and webhooks." },
      { h2: "Try it free" },
      { p: "The free plan includes 5 documents per month with no credit card required. Upload a bank statement and download a clean CSV in seconds." },
    ],
    faqs: [
      { q: "Can I convert a scanned bank statement to CSV?", a: "Yes. InvoiceParsed uses AI vision models that read both digital and scanned (image-based) bank statement PDFs, so older scans and photos work too." },
      { q: "Will the running balance be included in the CSV?", a: "Yes. Each transaction row includes date, description, debit/credit and the running balance, so the export reconciles against the statement's closing balance." },
      { q: "Is there a free way to convert a bank statement PDF online?", a: "Yes. InvoiceParsed's free plan lets you convert up to 5 documents per month online with no credit card required." },
    ],
  },
  {
    slug: "import-invoices-into-quickbooks",
    title: "How to Import Invoices into QuickBooks (2026 Guide)",
    description:
      "Learn how to import invoices and bills into QuickBooks fast. Use AI to turn invoice PDFs into a QuickBooks-ready CSV (Bill No, Date, Terms, Qty, Rate, Amount) and import in minutes.",
    excerpt:
      "To import invoices into QuickBooks, extract the invoice data with an AI parser like InvoiceParsed, which exports a CSV using QuickBooks bill/invoice column names (Bill No, Bill Date, Due Date, Terms, Description, Qty, Rate, Amount, Tax, Total). Then upload that CSV through the QuickBooks import wizard — no manual entry.",
    author: "InvoiceParsed Team",
    datePublished: "2026-06-17",
    dateModified: "2026-06-17",
    image: "/og/blog/import-invoices-into-quickbooks.png",
    tags: ["QuickBooks", "invoice import", "accounting"],
    content: [
      { h2: "The problem with entering invoices into QuickBooks by hand" },
      { p: "QuickBooks doesn't read PDFs — it expects you to key in each bill and invoice, line by line. At any real volume that's hours of typing every month, and every manual entry is a chance to fat-finger a total or a tax figure. The fix is to get your invoices into a CSV QuickBooks can import, instead of typing them." },
      { h2: "The fastest method: extract, then import a CSV" },
      { ol: [
        "Upload your invoice PDFs to an AI parser.",
        "Export a CSV that uses QuickBooks' bill/invoice column names.",
        "Open QuickBooks → import the CSV through the bill/invoice import wizard and map the columns.",
      ] },
      { p: "InvoiceParsed exports a CSV with QuickBooks-compatible headers (Bill No, Bill Date, Due Date, Terms, Description, Qty, Rate, Amount, Tax, Total), so the columns line up in the wizard with little or no remapping." },
      { h2: "Which fields map to QuickBooks" },
      { ul: [
        "Vendor → Vendor/Supplier",
        "Invoice number → Bill No",
        "Invoice date and due date → Bill Date / Due Date",
        "Payment terms → Terms",
        "Line items → Description, Qty, Rate, Amount",
        "Tax and total → Tax / Total",
      ] },
      { h2: "QuickBooks Online vs Desktop" },
      { p: "QuickBooks Online imports bills and invoices from CSV directly. QuickBooks Desktop typically imports via CSV through a built-in or add-on importer, and also supports IIF for batch entries. Either way, the key is starting from a clean, correctly-labelled CSV — which is exactly what the extraction step produces, so you're not fighting the importer." },
      { h2: "Tips for a clean import" },
      { ul: [
        "Make sure vendor names in the CSV match how they're spelled in QuickBooks, or create them on import.",
        "Check the date format expected by your QuickBooks region before importing.",
        "Use the per-field confidence scores to review totals and tax before you import, not after.",
      ] },
      { h2: "Automating it end to end" },
      { p: "If you process invoices continuously, you can skip the manual CSV step: InvoiceParsed's REST API and webhooks return the same structured data as JSON, which you can push into QuickBooks via its API or a tool like Zapier — so new invoices flow in without anyone touching a keyboard." },
      { h2: "Try it free" },
      { p: "The free plan includes 5 invoices per month with no credit card required. Upload an invoice, export the QuickBooks CSV, and run a test import in minutes." },
    ],
    faqs: [
      { q: "Can QuickBooks import invoices from a PDF?", a: "Not directly — QuickBooks imports structured CSV/Excel, not PDFs. InvoiceParsed bridges the gap by extracting the PDF into a QuickBooks-compatible CSV you can import." },
      { q: "Does this work with QuickBooks Online and Desktop?", a: "Yes. The exported CSV uses standard bill/invoice column names that work with the QuickBooks Online importer and Desktop CSV/IIF import workflows." },
      { q: "Can I automate invoice import into QuickBooks?", a: "Yes. InvoiceParsed's REST API and webhooks return structured JSON you can push into QuickBooks via its API or an automation tool like Zapier, with no manual CSV step." },
    ],
  },
  {
    slug: "docparser-alternatives",
    title: "5 Best Docparser Alternatives in 2026 (Compared)",
    description:
      "Looking for a Docparser alternative? Compare the best document and invoice parsing tools in 2026 on accuracy, template-free AI extraction, pricing and API access.",
    excerpt:
      "The best Docparser alternatives in 2026 replace rule- and template-based parsing with AI that reads invoices and receipts across any layout. For freelancers and small teams, InvoiceParsed offers template-free extraction, per-field confidence scores and a free tier; other alternatives suit higher-volume or enterprise workflows.",
    author: "InvoiceParsed Team",
    datePublished: "2026-06-17",
    dateModified: "2026-06-17",
    image: "/og/blog/docparser-alternatives.png",
    tags: ["Docparser alternative", "comparison", "invoice parsing"],
    content: [
      { h2: "Why look for a Docparser alternative?" },
      { p: "Docparser is a capable document-parsing tool, but it leans on parsing rules and zones you configure per layout. That works well for a handful of fixed formats — and becomes a maintenance burden when vendors keep changing how their invoices look. Many teams switch to AI-based parsers that read documents without templates, so a new vendor format just works." },
      { h2: "What to look for in an alternative" },
      { ul: [
        "Template-free AI extraction across varied layouts",
        "Structured export — JSON and accounting-ready CSV",
        "Per-field confidence so you know what to review",
        "API and webhooks for automation",
        "A real free tier and pricing that fits your volume",
      ] },
      { h2: "1. InvoiceParsed — best for freelancers and small teams" },
      { p: "AI extraction with no rules or zones to configure: upload an invoice, receipt or bank statement and get structured fields back with per-field confidence scores. Exports QuickBooks-compatible CSV and JSON, with a REST API and webhooks on paid plans. Starts free (5 documents/month) and is set up in minutes — the closest fit if you switched away from Docparser to escape template maintenance." },
      { h2: "2. Enterprise IDP platforms" },
      { p: "Intelligent document-processing suites aimed at large finance teams offer deep workflow and ERP integrations and human-in-the-loop review. Powerful, but enterprise pricing and onboarding make them overkill for most freelancers and SMBs." },
      { h2: "3. General-purpose OCR APIs" },
      { p: "Cloud OCR APIs return text and bounding boxes cheaply, but you build the logic to turn that into invoice fields yourself. A fit for developers who want full control, less so for teams that just want clean data out of the box." },
      { h2: "4. AI document-extraction APIs" },
      { p: "A newer class of AI extraction APIs accepts a schema and returns structured data without templates. Good for engineering teams building a custom pipeline; you'll still write integration and review tooling around them." },
      { h2: "5. Accounting-suite capture add-ons" },
      { p: "Some accounting platforms bundle invoice/receipt capture. Convenient if you're locked into that suite, but typically weaker on multi-format export and API flexibility than a dedicated parser." },
      { h2: "How to choose" },
      { ul: [
        "Tired of maintaining templates → pick a template-free AI parser.",
        "Developer building a pipeline → prioritise API + webhooks + JSON schema.",
        "Large enterprise with ERP needs → evaluate an IDP platform.",
      ] },
      { h2: "Bottom line" },
      { p: "If you're leaving Docparser to stop maintaining parsing rules, an AI parser like InvoiceParsed gives you template-free extraction with accounting-ready export and a free tier to test against your real documents before you commit." },
    ],
    faqs: [
      { q: "What is the main difference between Docparser and AI parsers?", a: "Docparser relies on parsing rules and zones you configure per layout, while AI parsers like InvoiceParsed read documents using vision models that understand layout and context — so they handle new and varied formats without templates." },
      { q: "Is there a free Docparser alternative?", a: "Yes. InvoiceParsed offers a free plan with 5 documents per month and no credit card required, so you can compare its output against your current Docparser setup." },
    ],
  },
  {
    slug: "nanonets-alternative",
    title: "InvoiceParsed: A Simpler Nanonets Alternative for Small Teams (2026)",
    description:
      "Looking for a Nanonets alternative? See how InvoiceParsed compares for invoice and receipt extraction — template-free AI, per-field confidence, simple pricing and a real free tier.",
    excerpt:
      "InvoiceParsed is a lightweight Nanonets alternative built for freelancers and small teams: template-free AI extraction for invoices, receipts and bank statements, per-field confidence scores, QuickBooks-ready CSV and a REST API — with a free tier and pricing that doesn't require sales calls or model training.",
    author: "InvoiceParsed Team",
    datePublished: "2026-06-17",
    dateModified: "2026-06-17",
    image: "/og/blog/nanonets-alternative.png",
    tags: ["Nanonets alternative", "comparison", "invoice parsing"],
    content: [
      { h2: "Why look for a Nanonets alternative?" },
      { p: "Nanonets is a powerful document-AI platform aimed at automating large, varied document workflows. That power comes with setup: training or configuring models, building workflows, and pricing geared toward higher-volume and enterprise use. If you're a freelancer or small team that just wants invoices and receipts turned into clean data, that can be more platform than you need." },
      { h2: "What small teams usually want instead" },
      { ul: [
        "Template-free extraction that works out of the box — no model training",
        "Invoice, receipt and bank statement support in one place",
        "Per-field confidence so you know exactly what to review",
        "Accounting-ready CSV (QuickBooks) and JSON export",
        "Transparent pricing with a free tier — no sales call to get started",
      ] },
      { h2: "How InvoiceParsed compares" },
      { p: "InvoiceParsed focuses on doing one job well: read a financial document and return structured fields. There's nothing to train — upload an invoice, receipt or bank statement and get labelled data back in seconds, each field with a confidence score. Export a QuickBooks-compatible CSV or JSON, or pull data via the REST API and webhooks on paid plans." },
      { h2: "Where each tool fits" },
      { ul: [
        "Large enterprise automating many document types with custom workflows → Nanonets.",
        "Freelancer or small finance team wanting invoices/receipts as clean data today → InvoiceParsed.",
        "Developer needing a simple POST-a-file, get-JSON-back API → InvoiceParsed's REST API.",
      ] },
      { h2: "Pricing and setup" },
      { p: "InvoiceParsed starts free (5 documents/month, no credit card) and uses simple volume-based plans you can sign up for directly. There's no model-training step and no required onboarding call — you can test it against your own documents in minutes." },
      { h2: "Bottom line" },
      { p: "If Nanonets feels like more platform — and more setup — than your workflow needs, InvoiceParsed gives you template-free invoice and receipt extraction with accounting-ready export and a free tier to try first. Upload a document and compare the output against your current process." },
    ],
    faqs: [
      { q: "Is InvoiceParsed a good Nanonets alternative for small businesses?", a: "Yes. InvoiceParsed is built for freelancers and small teams who want invoices, receipts and bank statements turned into clean data without training models or enterprise onboarding, with a free tier to start." },
      { q: "Do I need to train a model like with Nanonets?", a: "No. InvoiceParsed uses template-free AI that reads documents out of the box, so there's no model training or per-layout configuration." },
    ],
  },
  {
    slug: "invoice-pdf-to-excel",
    title: "How to Convert an Invoice PDF to Excel (2026 Guide)",
    description:
      "Convert invoice PDFs to Excel automatically with AI. Turn line items, totals and tax into structured spreadsheet rows in seconds — no manual typing, no broken copy-paste.",
    excerpt:
      "To convert an invoice PDF to Excel, upload it to an AI parser like InvoiceParsed, which reads the invoice and returns structured fields — vendor, line items, quantity, unit price, tax and total — as a CSV/Excel file you can open directly in Excel or Google Sheets in seconds, with no manual typing or messy copy-paste.",
    author: "InvoiceParsed Team",
    datePublished: "2026-06-17",
    dateModified: "2026-06-17",
    image: "/og/blog/invoice-pdf-to-excel.png",
    tags: ["invoice to Excel", "spreadsheet", "automation"],
    content: [
      { h2: "Why copy-pasting an invoice PDF into Excel fails" },
      { p: "PDFs store text by position on the page, not as a table. So when you copy an invoice and paste it into Excel, line items collapse into a single cell, columns merge, and wrapped descriptions land in the wrong rows. You end up cleaning up the mess by hand — which defeats the point. The reliable fix is to extract the invoice into structured columns first." },
      { h2: "The fastest method: an AI parser" },
      { ol: [
        "Upload the invoice PDF (or a photo/scan).",
        "The AI reads it and maps every field into structured columns.",
        "Download as a CSV/Excel file and open it directly in Excel or Google Sheets.",
      ] },
      { p: "InvoiceParsed keeps each line item on its own row — even when a description wraps across lines — so the spreadsheet is ready to sort, sum and filter without cleanup." },
      { h2: "What columns you get" },
      { ul: [
        "Vendor name and details",
        "Invoice number, invoice date and due date",
        "Line items — description, quantity, unit price, amount",
        "Subtotal, tax and total",
        "Currency and payment terms",
      ] },
      { h2: "CSV vs native Excel" },
      { p: "A CSV opens directly in Excel and Google Sheets and is the most portable format, which is why InvoiceParsed exports CSV by default. Once it's open you can save it as .xlsx, add formulas, or paste it into an existing tracker — the data is already in clean columns, so nothing breaks." },
      { h2: "Tips for accurate output" },
      { ul: [
        "Upload the clearest copy you have — sharp scans beat blurry photos.",
        "Keep multi-page invoices together so totals reconcile.",
        "Use the per-field confidence scores to spot anything worth a quick check before you build formulas on top.",
      ] },
      { h2: "Doing it in bulk" },
      { p: "If you have a stack of invoices, you don't want to repeat this one file at a time. InvoiceParsed lets you process invoices in volume and export combined data, or pull structured JSON via the REST API to drop straight into a spreadsheet or database automatically." },
      { h2: "Try it free" },
      { p: "The free plan includes 5 invoices per month with no credit card required. Upload an invoice PDF and download a clean Excel-ready file in seconds." },
    ],
    faqs: [
      { q: "Can I convert a scanned invoice PDF to Excel?", a: "Yes. InvoiceParsed reads both digital and scanned (image-based) invoice PDFs using AI vision models, so photos and scans convert to a spreadsheet too." },
      { q: "Why do line items break when I paste a PDF into Excel?", a: "PDFs store text by position, not as a table, so copy-paste collapses columns and rows. An AI parser reconstructs the invoice as structured columns, keeping each line item on its own row." },
      { q: "Does it export .xlsx or CSV?", a: "InvoiceParsed exports CSV, which opens directly in Excel and Google Sheets and can be saved as .xlsx. JSON export is also available via the API." },
    ],
  },
  {
    slug: "invoice-ocr-api",
    title: "Invoice OCR API: Extract Invoice Data Programmatically (2026 Guide)",
    description:
      "Use an invoice OCR API to extract structured invoice data in code. POST a PDF, get clean JSON back — vendor, line items, tax and total — with confidence scores and webhooks.",
    excerpt:
      "An invoice OCR API lets you extract structured invoice data programmatically: POST a PDF or image to an endpoint and get clean JSON back — vendor, invoice number, dates, line items, tax and total — each with a confidence score. InvoiceParsed offers a REST API with webhooks so you can automate invoice processing inside your own app or accounting workflow.",
    author: "InvoiceParsed Team",
    datePublished: "2026-06-17",
    dateModified: "2026-06-17",
    image: "/og/blog/invoice-ocr-api.png",
    tags: ["invoice OCR API", "developers", "automation"],
    content: [
      { h2: "What is an invoice OCR API?" },
      { p: "An invoice OCR API is an HTTP endpoint you send an invoice file to and get structured data back in code — no UI, no manual upload. Plain OCR APIs return raw text and bounding boxes; an invoice extraction API goes further and returns labelled fields (vendor, dates, line items, tax, total) ready to use in your application or pipeline." },
      { h2: "How it works" },
      { ol: [
        "POST the invoice file (PDF or image) to the extract endpoint with your API key.",
        "The service reads the document and maps it into a structured schema.",
        "You receive JSON — fields plus per-field confidence — synchronously or via webhook for larger documents.",
      ] },
      { p: "With InvoiceParsed it's a single authenticated POST. Here's the shape of a request:" },
      { ul: [
        "POST https://api.invoiceparsed.com/extract",
        "Header: Authorization: Bearer YOUR_API_KEY",
        "Body: multipart form field file=@invoice.pdf",
        "Response: 200 OK with JSON { vendor, invoice_number, dates, line_items[], tax, total }",
      ] },
      { h2: "What the JSON contains" },
      { ul: [
        "Vendor — name, address, contact",
        "Invoice number, invoice date and due date",
        "Currency and payment terms",
        "Line items — description, quantity, unit price, amount",
        "Subtotal, tax, total — each field with a confidence score",
      ] },
      { h2: "Synchronous responses vs webhooks" },
      { p: "Small invoices return results in the same request, which is simplest to integrate. For batches or large multi-page documents, register a webhook so the API notifies your server when extraction finishes instead of holding the connection open — the standard pattern for asynchronous document processing at scale." },
      { h2: "Common use cases" },
      { ul: [
        "Auto-creating bills in accounting software from emailed invoices",
        "Powering an AP (accounts-payable) automation workflow",
        "Adding 'upload an invoice' to your own SaaS product",
        "Feeding a data warehouse or ERP without manual entry",
      ] },
      { h2: "Choosing an invoice OCR API" },
      { ul: [
        "Returns structured fields, not just raw text",
        "Per-field confidence scores so you can route low-confidence docs to review",
        "Webhooks for asynchronous and batch processing",
        "Predictable, volume-based pricing with a free tier to prototype",
      ] },
      { h2: "Get an API key" },
      { p: "API access is available on InvoiceParsed's Pro plan, and you can prototype against the free tier first. Read the API docs, grab a key, and you can be extracting structured invoice data from code in a few minutes." },
    ],
    faqs: [
      { q: "What's the difference between an OCR API and an invoice extraction API?", a: "A plain OCR API returns raw text and coordinates from an image; an invoice extraction API like InvoiceParsed returns labelled, structured fields (vendor, line items, tax, total) as JSON, so you don't have to parse the text yourself." },
      { q: "Does the invoice OCR API support webhooks?", a: "Yes. InvoiceParsed supports webhooks so larger or batched documents can be processed asynchronously and your server is notified when results are ready." },
      { q: "Is there a free way to try the invoice OCR API?", a: "You can prototype on the free tier, and full API access is available on the Pro plan. See the API docs to get a key and start extracting." },
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
