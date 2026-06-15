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
    "Stop typing invoices into spreadsheets. Upload a PDF or photo and get vendor, line items, taxes and totals as structured JSON or CSV — instantly, accurately, automatically.",
  primaryCta: { label: "Extract your first invoice", to: "/signup" },
  secondaryCta: { label: "See how it works", href: "#how" },
  trust: ["< 5 sec average", "95%+ accuracy", "No credit card · 5 free invoices"],
};

// Answer-first paragraph for AEO (answer engines / featured snippets). Kept
// visually subtle on the page but crawler-visible, and baked into the static HTML.
export const ANSWER =
  "InvoiceParsed is an AI-powered tool that extracts data from invoices, receipts and bank statements — turning a PDF or image into structured data (vendor, line items, tax and totals) in seconds. Upload a file and export to Excel, a QuickBooks-compatible CSV, or JSON, with a confidence score on every field. No templates, no manual data entry.";

export const STATS = [
  ["5 sec", "Avg. processing"],
  ["95%+", "Field accuracy"],
  ["10+", "Fields per invoice"],
  ["JSON/CSV", "Export formats"],
];

export const FEATURES = [
  { icon: "ScanLine", title: "Field-perfect extraction", desc: "Vendor, invoice number, dates, line items, subtotal, tax and total — every field, captured accurately." },
  { icon: "Layers", title: "PDF & image, any layout", desc: "Upload PDFs or photos. Handles messy scans, multi-page invoices and unusual layouts." },
  { icon: "FileJson", title: "Excel, CSV & JSON export", desc: "One click to an Excel (.xlsx) workbook, a QuickBooks-compatible CSV, or a strict JSON payload — straight into your accounting software." },
  { icon: "Gauge", title: "95%+ accuracy", desc: "Tuned prompts and structured outputs keep extraction reliable on standard invoice formats." },
  { icon: "Clock", title: "Seconds, not hours", desc: "What took a bookkeeper 6 hours a week now happens the moment you drop a file." },
  { icon: "ShieldCheck", title: "Private by design", desc: "Your documents are processed for extraction only — no training, no resale of your data." },
];

export const STEPS = [
  { icon: "Upload", title: "Upload", desc: "Drag & drop a PDF or image, or pick a file. Up to 10MB per invoice." },
  { icon: "ScanLine", title: "Extract", desc: "Our AI reads the document and structures every field in seconds." },
  { icon: "FileJson", title: "Export", desc: "Review, edit, then download JSON or CSV — or pull it via the API." },
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
    desc: "Process invoices at volume and feed them straight into your accounting stack. Batch upload, REST API, webhooks and centralized billing.",
    points: ["Batch & multi-page", "REST API + webhooks", "High-volume processing", "Centralized billing"],
  },
];
