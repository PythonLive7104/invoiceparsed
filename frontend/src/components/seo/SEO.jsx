import { Helmet } from "react-helmet-async";
import { SITE, absoluteUrl, clamp } from "@/content/site";

/**
 * Reusable SEO head: title, meta description, canonical, Open Graph and Twitter
 * Card tags. Drop one <SEO /> at the top of every page.
 *
 * Props:
 *   title        page title (a " — InvoiceParsed" suffix is added unless titleRaw)
 *   description  meta description (clamped to 155 chars)
 *   path         canonical path, e.g. "/pricing" (defaults to current location is
 *                NOT auto-derived to keep SSR-safe — always pass it)
 *   image        social image path/URL (defaults to site OG image)
 *   type         Open Graph type: "website" (default) | "article"
 *   noindex      adds <meta name="robots" content="noindex,follow">
 *   titleRaw     use the title exactly, without the brand suffix
 *   article      { publishedTime, modifiedTime, author, tags } for og:article
 */
export function SEO({
  title,
  description,
  path = "/",
  image = SITE.ogImage,
  type = "website",
  noindex = false,
  titleRaw = false,
  article,
}) {
  const fullTitle = titleRaw
    ? title
    : title
      ? `${title} — ${SITE.name}`
      : `${SITE.name} — AI invoice data extraction`;
  // Keep meta titles under ~60 chars; warn-free clamp at the boundary.
  const metaTitle = clamp(fullTitle, 60);
  const metaDesc = clamp(description || SITE.description, 155);
  const canonical = absoluteUrl(path);
  const ogImage = absoluteUrl(image);

  return (
    <Helmet prioritizeSeoTags>
      <title>{fullTitle}</title>
      <meta name="description" content={metaDesc} />
      <link rel="canonical" href={canonical} />
      {noindex ? (
        <meta name="robots" content="noindex,follow" />
      ) : (
        <meta name="robots" content="index,follow,max-image-preview:large" />
      )}

      {/* Open Graph */}
      <meta property="og:site_name" content={SITE.name} />
      <meta property="og:type" content={type} />
      <meta property="og:title" content={metaTitle} />
      <meta property="og:description" content={metaDesc} />
      <meta property="og:url" content={canonical} />
      <meta property="og:image" content={ogImage} />
      <meta property="og:locale" content={SITE.locale} />
      {type === "article" && article?.publishedTime && (
        <meta property="article:published_time" content={article.publishedTime} />
      )}
      {type === "article" && article?.modifiedTime && (
        <meta property="article:modified_time" content={article.modifiedTime} />
      )}
      {type === "article" &&
        (article?.tags || []).map((tag) => (
          <meta key={tag} property="article:tag" content={tag} />
        ))}

      {/* Twitter */}
      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:site" content={SITE.twitter} />
      <meta name="twitter:title" content={metaTitle} />
      <meta name="twitter:description" content={metaDesc} />
      <meta name="twitter:image" content={ogImage} />
    </Helmet>
  );
}
