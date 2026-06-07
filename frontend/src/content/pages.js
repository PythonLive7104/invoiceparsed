// SEO metadata for the non-article static pages. Single source of truth shared
// by the React <SEO> components and the build-time prerenderer, so the runtime
// head and the static (crawler-visible) head never drift apart. Pure JS.

export const PAGE_META = {
  "/": {
    title: "AI invoice data extraction software",
    description:
      "InvoiceParsed is an AI invoice parser that extracts data from invoice PDFs and images in seconds. Export clean JSON or CSV. Free plan, no card.",
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
  "/blog": {
    title: "Blog — invoice automation guides",
    description:
      "Guides on AI invoice extraction, OCR, and automating invoice data entry for freelancers and small businesses.",
    schema: [],
  },
};
