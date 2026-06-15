// SEO metadata for the non-article static pages. Single source of truth shared
// by the React <SEO> components and the build-time prerenderer, so the runtime
// head and the static (crawler-visible) head never drift apart. Pure JS.

export const PAGE_META = {
  "/": {
    title: "AI invoice, receipt & statement extraction",
    description:
      "AI parser for invoices, receipts & bank statements — no templates. Turn a PDF or image into clean CSV/JSON in seconds. Free plan, paid from $19/mo.",
    schema: ["software", "faq"],
  },
  "/pricing": {
    title: "Pricing — InvoiceParsed",
    titleRaw: true,
    description:
      "Pricing for invoice, receipt and bank statement extraction. Start free with 5 documents/month, then scale to Starter, Pro and Business with API access.",
    schema: ["faq"],
  },
  "/about": {
    title: "About InvoiceParsed",
    description:
      "InvoiceParsed helps freelancers and small businesses eliminate manual data entry from invoices, receipts and bank statements with fast, accurate AI extraction. Learn about our mission.",
    schema: [],
  },
  "/faq": {
    title: "InvoiceParsed FAQ — AI invoice extraction questions",
    titleRaw: true,
    description:
      "Answers to common questions about InvoiceParsed: accuracy, supported formats for invoices, receipts and bank statements, pricing, the free plan, API access and more.",
    schema: ["faq"],
  },
  "/docs": {
    title: "API Documentation — InvoiceParsed",
    titleRaw: true,
    description:
      "InvoiceParsed REST API docs: extract invoices, receipts and bank statements via /api/extract. Auth, endpoints, code examples (cURL, Python, Node.js) and webhooks.",
    schema: [],
  },
  "/contact": {
    title: "Contact InvoiceParsed",
    description:
      "Get in touch with the InvoiceParsed team — questions about invoice, receipt or bank statement extraction, pricing, the API, or your account.",
    schema: [],
  },
  "/blog": {
    title: "Blog — invoice automation guides",
    description:
      "Guides on AI extraction for invoices, receipts and bank statements, OCR, and automating financial data entry for freelancers and small businesses.",
    schema: [],
  },
  "/compare": {
    title: "Comparisons — InvoiceParsed",
    titleRaw: true,
    description:
      "How InvoiceParsed compares to manual data entry and traditional OCR for extracting invoice, receipt and bank statement data.",
    schema: [],
  },
  "/use-cases": {
    title: "Use cases — InvoiceParsed",
    titleRaw: true,
    description:
      "How freelancers, small businesses and finance teams use InvoiceParsed to automate invoice, receipt and bank statement data extraction.",
    schema: [],
  },
};
