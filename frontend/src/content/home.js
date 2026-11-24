// Homepage marketing content — single source of truth shared by the React
// landing page (Hero/Landing) and the build-time prerenderer, so the live app
// and the crawler-visible static HTML never drift. Pure JS (no JSX/aliases) so
// scripts/prerender.mjs can import it at build time. Icons are referenced by
// lucide-react export name and mapped to components in the React components.

export const HERO = {
  eyebrow: "AI extraction for invoices, receipts & statements",
  // Title is split so the React Hero can style the highlight, while the
  // prerenderer can emit a plain <h1> with the same words.
  title: { lead: "Turn any invoice into ", highlight: "clean data", tail: " in seconds." },
  subhead:
    "Stop typing invoices into spreadsheets. Upload a PDF or photo and get vendor, line items, taxes and totals as structured JSON or CSV — then match each invoice against your purchase orders before you pay it.",
  primaryCta: { label: "Extract your first invoice", to: "/signup" },
  secondaryCta: { label: "See how it works", href: "#how" },
  trust: ["< 5 sec average", "95%+ accuracy", "No credit card · 5 free invoices"],
};

// Answer-first paragraph for AEO (answer engines / featured snippets). Kept
// visually subtle on the page but crawler-visible, and baked into the static HTML.
export const ANSWER =
  "InvoiceParsed is an AI-powered tool that extracts data from invoices, receipts and bank statements — turning a PDF or image into structured data (vendor, line items, tax and totals) in seconds. Upload a file and export to Excel, a QuickBooks-compatible CSV, or JSON, with a confidence score on every field. No templates, no manual data entry. On the Pro plan it also runs the accounts-payable work that follows: supplier records, purchase orders with approval, and automatic invoice-to-PO matching that flags price changes, over-invoicing and anything billed against an order nobody approved.";

export const STATS = [
  ["5 sec", "Avg. processing"],
  ["95%+", "Field accuracy"],
  ["3-way", "Invoice ↔ PO checks"],
  ["JSON/CSV", "Export formats"],
];

export const FEATURES = [
  { icon: "ScanLine", title: "Field-perfect extraction", desc: "Vendor, invoice number, dates, line items, subtotal, tax and total — every field, captured accurately." },
  { icon: "Layers", title: "PDF & image, any layout", desc: "Upload PDFs or photos. Handles messy scans, multi-page invoices and unusual layouts." },
  { icon: "FileJson", title: "Excel, CSV & JSON export", desc: "One click to an Excel (.xlsx) workbook, a QuickBooks-compatible CSV, or a strict JSON payload — straight into your accounting software." },
  { icon: "Clock", title: "Seconds, not hours", desc: "What took a bookkeeper 6 hours a week now happens the moment you drop a file." },
  { icon: "GitCompareArrows", title: "Invoice-to-PO matching", desc: "Pro: every invoice checked against the order it bills. Price rises, over-invoicing and lines nobody ordered are flagged before payment." },
  { icon: "ShieldCheck", title: "Private by design", desc: "Your documents are processed for extraction only — no training, no resale of your data." },
];

// The accounts-payable module (Pro and above). Separate from FEATURES because
// it is a different promise: FEATURES is "we read your documents accurately",
// this is "we tell you whether to pay them". Collapsing the two would bury the
// second in a grid of nine cards.
export const PAYABLES_SECTION = {
  eyebrow: "Pro plan",
  title: "Then decide whether to pay it",
  blurb:
    "Extraction tells you what an invoice says. Accounts payable tells you whether it matches what you agreed to buy — the oldest control in finance, and the one spreadsheets cannot do.",
  features: [
    {
      icon: "Building2",
      title: "Supplier records",
      desc: "One record per business you buy from, built automatically as invoices arrive. Spend totalled per supplier and per currency, duplicate suppliers flagged on tax ID and name, and bank details held behind their own permission so a scanned document can never silently change where money goes.",
    },
    {
      icon: "ClipboardList",
      title: "Purchase orders",
      desc: "Record what you agreed to buy, with line items, taxes and delivery dates. Totals are computed from the lines, never accepted from a form. Approval is a separate permission from raising an order, and nobody can approve an order they raised themselves. Send the supplier a PDF that marks anything unapproved as not an authorization to supply.",
    },
    {
      icon: "GitCompareArrows",
      title: "Invoice matching",
      desc: "Each arriving invoice is linked to its order and compared line by line — unit prices, quantities, tax rates and totals. Price rises, quantities above what was ordered, lines nobody ordered and invoices billed against an unapproved order are all flagged with both figures named. Over-invoicing is caught across several invoices, not just within one.",
    },
    {
      icon: "ShieldCheck",
      title: "Controls that hold",
      desc: "Tolerances you set, so ordinary rounding does not cry wolf. Eight roles, so the person entering invoices is not the person approving them. A discrepancy can be accepted — but only by someone with approval authority, only with a written reason, and the finding stays on the record with their name against it.",
    },
  ],
};

export const STEPS = [
  { icon: "Upload", title: "Upload", desc: "Drag & drop a PDF or image, or pick a file. Up to 10MB per invoice." },
  { icon: "ScanLine", title: "Extract", desc: "Our AI reads the document and structures every field in seconds." },
  { icon: "FileJson", title: "Export", desc: "Review, edit, then download Excel, CSV or JSON — or pull it via the API." },
  { icon: "GitCompareArrows", title: "Check", desc: "On Pro, the invoice is matched against your purchase order and anything that does not agree is flagged before you pay." },
];

export const AUDIENCES = [
  {
    id: "personal",
    icon: "User",
    eyebrow: "For individuals",
    title: "Freelancers & sole traders",
    desc: "Stop logging client invoices into a spreadsheet by hand. Drag in a PDF, get clean data and a CSV in seconds — and reclaim hours every week.",
    points: ["Simple drag & drop", "CSV export for your books", "Accurate line-item capture", "Starts free"],
  },
  {
    id: "business",
    icon: "Building2",
    eyebrow: "For businesses",
    title: "Teams, agencies & finance ops",
    desc: "Run the whole payables cycle, not just the data entry: suppliers, purchase orders, approvals and invoice matching, with batch upload, a REST API and webhooks feeding your accounting stack.",
    points: ["Suppliers, POs & invoice matching", "Approvals with roles & permissions", "REST API + webhooks", "Centralized billing"],
  },
];
