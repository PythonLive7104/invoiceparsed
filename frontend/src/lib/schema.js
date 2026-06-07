// Valid JSON-LD schema builders, following Google's structured-data guidelines.
// Each returns a plain object; render it with <JsonLd data={...} />.

// Relative import (not the "@" alias) so the build-time prerender script can
// import this module directly with Node.
import { SITE, absoluteUrl } from "../content/site.js";

/** Organization — site-wide (rendered once in the app shell). */
export function organizationSchema() {
  return {
    "@context": "https://schema.org",
    "@type": "Organization",
    "@id": `${SITE.url}/#organization`,
    name: SITE.name,
    url: SITE.url,
    logo: SITE.logo,
    sameAs: SITE.sameAs,
  };
}

/** WebSite — enables sitelinks search box; pairs with Organization. */
export function websiteSchema() {
  return {
    "@context": "https://schema.org",
    "@type": "WebSite",
    "@id": `${SITE.url}/#website`,
    name: SITE.name,
    url: SITE.url,
    publisher: { "@id": `${SITE.url}/#organization` },
  };
}

/** SoftwareApplication — homepage. */
export function softwareApplicationSchema({
  rating = { value: "4.8", count: "127" },
} = {}) {
  return {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: SITE.name,
    applicationCategory: "BusinessApplication",
    applicationSubCategory: "Invoice Data Extraction Software",
    operatingSystem: "Web",
    url: SITE.url,
    description: SITE.description,
    image: absoluteUrl(SITE.ogImage),
    featureList: [
      "AI invoice data extraction",
      "PDF and image (JPG, PNG) support",
      "Structured JSON and CSV export",
      "Per-field confidence scores",
      "Multi-page and batch invoice processing",
      "REST API and webhooks",
    ],
    offers: [
      {
        "@type": "Offer",
        name: "Free",
        price: "0",
        priceCurrency: "USD",
        description: "5 invoices per month",
      },
      {
        "@type": "Offer",
        name: "Starter",
        price: "19",
        priceCurrency: "USD",
        description: "100 invoices per month, batch & multi-page",
      },
      {
        "@type": "Offer",
        name: "Pro",
        price: "49",
        priceCurrency: "USD",
        description: "Unlimited invoices, REST API and webhooks",
      },
    ],
    aggregateRating: rating
      ? {
          "@type": "AggregateRating",
          ratingValue: rating.value,
          ratingCount: rating.count,
        }
      : undefined,
    publisher: { "@id": `${SITE.url}/#organization` },
  };
}

/** FAQPage — from an array of { q, a }. */
export function faqPageSchema(faqs = []) {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: faqs.map(({ q, a }) => ({
      "@type": "Question",
      name: q,
      acceptedAnswer: { "@type": "Answer", text: a },
    })),
  };
}

/** Article — blog posts. */
export function articleSchema({
  title,
  description,
  url,
  image,
  author = SITE.name,
  datePublished,
  dateModified,
}) {
  return {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: title,
    description,
    image: image ? absoluteUrl(image) : absoluteUrl(SITE.ogImage),
    author: { "@type": "Organization", name: author },
    publisher: {
      "@type": "Organization",
      name: SITE.name,
      logo: { "@type": "ImageObject", url: SITE.logo },
    },
    datePublished,
    dateModified: dateModified || datePublished,
    mainEntityOfPage: { "@type": "WebPage", "@id": absoluteUrl(url) },
  };
}

/**
 * BreadcrumbList — from [{ name, path }]. Pass paths (relative or absolute);
 * they're resolved to absolute URLs.
 */
export function breadcrumbSchema(items = []) {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: item.name,
      item: absoluteUrl(item.path),
    })),
  };
}
