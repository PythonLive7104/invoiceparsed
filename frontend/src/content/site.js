// Central SEO/site configuration. Pure JS (no JSX/aliases) so the sitemap
// generator script can import it at build time too.

export const SITE = {
  name: "InvoiceParsed",
  // Canonical origin — no trailing slash.
  url: "https://invoiceparsed.com",
  // Default social share image (1200x630). Place the asset in /public.
  ogImage: "/og/invoiceparsed-og.png",
  twitter: "@invoiceparsed",
  locale: "en_US",
  description:
    "InvoiceParsed is an AI invoice parser that extracts structured data from invoice PDFs and images in seconds — export clean JSON or CSV.",
  // Used by Organization schema.
  logo: "https://invoiceparsed.com/logo-512.png",
  sameAs: [
    "https://twitter.com/invoiceparsed",
    "https://www.linkedin.com/company/invoiceparsed",
  ],
};

/** Absolute URL for a path (canonical/OG use absolute URLs). */
export function absoluteUrl(path = "/") {
  if (/^https?:\/\//.test(path)) return path;
  return `${SITE.url}${path.startsWith("/") ? "" : "/"}${path}`;
}

/** Clamp a string to a max length without cutting mid-word, adding nothing. */
export function clamp(text = "", max = 155) {
  if (text.length <= max) return text;
  return text.slice(0, max).replace(/\s+\S*$/, "").trim();
}
