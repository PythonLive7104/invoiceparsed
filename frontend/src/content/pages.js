// SEO metadata for the non-article static pages. Single source of truth shared
// by the React <SEO> components and the build-time prerenderer, so the runtime
// head and the static (crawler-visible) head never drift apart. Pure JS.

export const PAGE_META = {
  "/": {
    title: "AI invoice, receipt & statement extraction",
    description:
      "AI parser for invoices, receipts and bank statements. Turn a PDF or image into clean structured data — export CSV or JSON in seconds. Free plan.",
    schema: ["software", "faq"],
  },
  "/pricing": {
    title: "Pricing — InvoiceParsed",
    titleRaw: true,
    description:
      "Simple invoice extraction pricing. Start free with 5 invoices/month, or scale to Starter, Pro and Business plans with batch, API and webhooks.",
    schema: ["faq"],
  },
  "/about": {
    title: "About InvoiceParsed",
    description:
      "InvoiceParsed helps freelancers and small businesses eliminate manual invoice data entry with fast, accurate AI extraction. Learn about our mission.",
    schema: [],
  },
  "/faq": {
    title: "InvoiceParsed FAQ — AI invoice extraction questions",
    titleRaw: true,
    description:
      "Answers to common questions about InvoiceParsed: accuracy, supported file formats, pricing, the free plan, API access and more.",
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
      "Guides on AI invoice extraction, OCR, and automating invoice data entry for freelancers and small businesses.",
    schema: [],
  },
  "/compare": {
    title: "Comparisons — InvoiceParsed",
    titleRaw: true,
    description:
      "How InvoiceParsed compares to manual data entry and traditional OCR for extracting invoice and receipt data.",
    schema: [],
  },
  "/use-cases": {
    title: "Use cases — InvoiceParsed",
    titleRaw: true,
    description:
      "How freelancers, small businesses and finance teams use InvoiceParsed to automate invoice and receipt data extraction.",
    schema: [],
  },
};
