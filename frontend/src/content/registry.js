// Content registry — the single source of truth for marketing routes.
// Both the React pages and the build-time sitemap generator import this, so
// adding an entry here automatically adds it to the sitemap.
//
// Pure JS (no JSX/aliases) so it can be imported by scripts/generate-sitemap.mjs.

// Static, always-present routes. `changefreq`/`priority` feed the sitemap.
// Only list routes that resolve to a real page — anything else soft-404s via the
// SPA catch-all and hurts crawl quality.
export const STATIC_ROUTES = [
  { path: "/", changefreq: "weekly", priority: 1.0 },
  { path: "/pricing", changefreq: "monthly", priority: 0.9 },
  { path: "/faq", changefreq: "monthly", priority: 0.7 },
  { path: "/about", changefreq: "yearly", priority: 0.5 },
  { path: "/blog", changefreq: "weekly", priority: 0.7 },
];

// Blog posts. `faqs` power both the on-page FAQ section and FAQPage JSON-LD.
export const BLOG_POSTS = [
  {
    slug: "extract-data-from-invoice-pdf",
    title: "How to Extract Data From an Invoice PDF (2026 Guide)",
    description:
      "Learn how to extract data from invoice PDFs automatically with AI — no manual data entry, no templates. Get clean JSON or CSV in seconds.",
    // Answer-first opening paragraph (AEO).
    excerpt:
      "To extract data from an invoice PDF, upload it to an AI invoice parser like InvoiceParsed, which reads the document and returns structured fields (vendor, line items, totals, tax) as JSON or CSV in seconds — no templates or manual entry required.",
    author: "InvoiceParsed Team",
    datePublished: "2026-01-15",
    dateModified: "2026-01-15",
    image: "/og/blog/extract-invoice-pdf.png",
    tags: ["invoice extraction", "PDF", "automation"],
    faqs: [
      {
        q: "Can I extract data from a scanned invoice PDF?",
        a: "Yes. InvoiceParsed uses AI vision models that read both digital and scanned (image-based) invoice PDFs, so handwritten-style scans and photos work too.",
      },
      {
        q: "What fields can be extracted from an invoice?",
        a: "Vendor name and address, invoice number, invoice and due dates, currency, line items (description, quantity, unit price, amount), subtotal, tax, and total — each with a confidence score.",
      },
      {
        q: "Is there a free way to parse invoice PDFs online?",
        a: "Yes. InvoiceParsed's free plan lets you parse up to 5 invoices per month online with no credit card required.",
      },
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
    dateModified: "2026-02-03",
    image: "/og/blog/invoice-ocr-tools.png",
    tags: ["invoice OCR", "comparison", "tools"],
    faqs: [
      {
        q: "What is invoice OCR?",
        a: "Invoice OCR (Optical Character Recognition) converts the text in an invoice image or PDF into machine-readable data. Modern AI tools go further, mapping that text into structured fields like totals and line items.",
      },
      {
        q: "Is AI invoice extraction more accurate than traditional OCR?",
        a: "Generally yes. Traditional OCR returns raw text; AI invoice parsers understand layout and context, so they correctly label vendors, dates and line items even across varied invoice formats.",
      },
    ],
  },
];

// Comparison pages (/compare/[slug]).
export const COMPARISONS = [
  {
    slug: "invoiceparsed-vs-manual-data-entry",
    title: "InvoiceParsed vs Manual Data Entry",
    description:
      "InvoiceParsed vs manual data entry: compare speed, accuracy and cost of AI invoice extraction against typing invoice data by hand.",
    excerpt:
      "InvoiceParsed extracts invoice data in seconds with per-field confidence scores, while manual data entry averages several minutes per invoice and is error-prone — automation wins on speed, accuracy and cost at any meaningful volume.",
    dateModified: "2026-03-01",
    faqs: [
      {
        q: "How much faster is AI invoice extraction than manual entry?",
        a: "AI extraction typically processes an invoice in a few seconds versus 2–5 minutes of manual typing, a 20–50x speedup before accounting for error correction.",
      },
    ],
  },
  {
    slug: "invoiceparsed-vs-traditional-ocr",
    title: "InvoiceParsed vs Traditional OCR Software",
    description:
      "InvoiceParsed vs traditional OCR: see why AI invoice parsing returns structured fields instead of raw text, with less setup and no templates.",
    excerpt:
      "Traditional OCR returns unstructured text you still have to parse, while InvoiceParsed returns labelled, structured invoice fields directly — removing template setup and post-processing for most small-business workflows.",
    dateModified: "2026-03-05",
    faqs: [
      {
        q: "Does InvoiceParsed require templates like older OCR tools?",
        a: "No. InvoiceParsed uses AI that understands invoice layouts, so it works across formats without per-vendor templates.",
      },
    ],
  },
];

// Use-case pages (/use-cases/[slug]).
export const USE_CASES = [
  {
    slug: "freelancers",
    title: "Invoice Data Extraction for Freelancers",
    description:
      "Automate invoice data entry as a freelancer. Upload client invoices and receipts, get clean structured data for bookkeeping and taxes in seconds.",
    excerpt:
      "Freelancers use InvoiceParsed to turn client invoices and receipts into structured data for bookkeeping and tax time — upload a PDF or photo and export clean JSON or CSV without manual typing.",
    dateModified: "2026-03-10",
    faqs: [
      {
        q: "Can freelancers use InvoiceParsed for free?",
        a: "Yes. The free plan covers 5 invoices per month, which is enough for many solo freelancers to handle monthly bookkeeping.",
      },
    ],
  },
  {
    slug: "small-business-accounting",
    title: "Invoice Extraction for Small Business Accounting",
    description:
      "Speed up small business accounting with automated invoice data extraction. Export to CSV or push to your accounting stack via the API.",
    excerpt:
      "Small businesses use InvoiceParsed to automate accounts-payable data entry — batch-upload supplier invoices, extract structured fields, and export to CSV or feed your accounting software through the REST API.",
    dateModified: "2026-03-12",
    faqs: [
      {
        q: "Can I connect InvoiceParsed to my accounting software?",
        a: "Yes. On the Pro plan you can use the REST API and webhooks to push extracted invoice data into your accounting or ERP system automatically.",
      },
    ],
  },
];

// FAQ shown on /pricing (also rendered as FAQPage JSON-LD).
export const PRICING_FAQS = [
  {
    q: "Is there a free plan?",
    a: "Yes. The Free plan includes 5 invoices per month with no credit card required — enough for many solo freelancers.",
  },
  {
    q: "Can I change plans later?",
    a: "Yes, you can upgrade or downgrade at any time from your dashboard; changes take effect immediately.",
  },
  {
    q: "What counts as one invoice?",
    a: "Each completed extraction counts as one invoice against your monthly limit. A multi-page PDF processed as a single invoice counts once.",
  },
  {
    q: "Do you offer an API?",
    a: "Yes. REST API access and webhooks are included on the Pro and Business plans for automating invoice processing.",
  },
];

// Site-wide FAQ shown on / and /faq (also rendered as FAQPage JSON-LD).
export const SITE_FAQS = [
  {
    q: "What is InvoiceParsed?",
    a: "InvoiceParsed is an AI-powered invoice data extraction tool. You upload an invoice PDF or image and it returns structured data — vendor, line items, tax and totals — as JSON or CSV in seconds.",
  },
  {
    q: "How accurate is AI invoice extraction?",
    a: "InvoiceParsed returns a confidence score (0–100%) for every field, so you can review low-confidence values. Accuracy is highest on clear digital PDFs and remains strong on photos and scans.",
  },
  {
    q: "Which file formats are supported?",
    a: "PDF, JPG and PNG files up to 10MB each. Multi-page PDFs and multi-file invoices are supported on paid plans.",
  },
  {
    q: "Is there a free plan?",
    a: "Yes — the free plan includes 5 invoices per month with no credit card required.",
  },
  {
    q: "Does InvoiceParsed work with QuickBooks?",
    a: "Yes. Every extraction can be exported as a QuickBooks-compatible CSV with bill/invoice columns (Bill No, Bill Date, Due Date, Terms, line-item Description/Qty/Rate/Amount, tax and total) that map cleanly in QuickBooks Online's CSV import. You can also export structured JSON or use the API.",
  },
];

/** Build the full list of sitemap entries from the registry. */
export function allRoutes() {
  const dynamic = [
    ...BLOG_POSTS.map((p) => ({
      path: `/blog/${p.slug}`,
      changefreq: "monthly",
      priority: 0.6,
      lastmod: p.dateModified,
    })),
    ...COMPARISONS.map((c) => ({
      path: `/compare/${c.slug}`,
      changefreq: "monthly",
      priority: 0.6,
      lastmod: c.dateModified,
    })),
    ...USE_CASES.map((u) => ({
      path: `/use-cases/${u.slug}`,
      changefreq: "monthly",
      priority: 0.6,
      lastmod: u.dateModified,
    })),
  ];
  return [...STATIC_ROUTES, ...dynamic];
}
