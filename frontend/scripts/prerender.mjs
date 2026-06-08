/**
 * Build-time prerenderer (no browser needed).
 *
 * Vite emits a single dist/index.html whose <head> is only refined at runtime by
 * react-helmet-async — invisible to crawlers that don't run JS (Bing, social
 * scrapers, some AI bots). This script writes a per-route static HTML file with
 * the correct <title>, meta, canonical, Open Graph/Twitter tags and JSON-LD
 * baked in, by replacing the <!-- SEO:START -->…<!-- SEO:END --> block and
 * injecting schema before </head>. The SPA still hydrates and takes over.
 *
 * On Vercel, static files are served before the SPA catch-all rewrite, so each
 * prerendered route is delivered with its own head; unknown routes fall back to
 * the default index.html.
 *
 *   node scripts/prerender.mjs        (run after `vite build`)
 */
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { SITE, absoluteUrl, clamp } from "../src/content/site.js";
import { PAGE_META } from "../src/content/pages.js";
import {
  BLOG_POSTS,
  COMPARISONS,
  USE_CASES,
  SITE_FAQS,
  PRICING_FAQS,
} from "../src/content/registry.js";
import {
  softwareApplicationSchema,
  faqPageSchema,
  articleSchema,
  breadcrumbSchema,
} from "../src/lib/schema.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const DIST = resolve(__dirname, "../dist");
const template = readFileSync(resolve(DIST, "index.html"), "utf8");

const esc = (s = "") =>
  String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/** Render registry content blocks to static HTML (mirrors ArticleBody.jsx). */
function blocksToHtml(blocks = []) {
  return blocks
    .map((b) => {
      if (b.h2) return `<h2>${esc(b.h2)}</h2>`;
      if (b.p) return `<p>${esc(b.p)}</p>`;
      if (b.ul) return `<ul>${b.ul.map((li) => `<li>${esc(li)}</li>`).join("")}</ul>`;
      if (b.ol) return `<ol>${b.ol.map((li) => `<li>${esc(li)}</li>`).join("")}</ol>`;
      return "";
    })
    .join("\n");
}

/** Full crawler-visible article HTML (title, intro, body, FAQ) injected into #root. */
function articleHtml(post) {
  const faq = post.faqs?.length
    ? `<section><h2>Frequently asked questions</h2>${post.faqs
        .map((f) => `<h3>${esc(f.q)}</h3><p>${esc(f.a)}</p>`)
        .join("")}</section>`
    : "";
  return (
    `<article><h1>${esc(post.title)}</h1>` +
    (post.excerpt ? `<p>${esc(post.excerpt)}</p>` : "") +
    blocksToHtml(post.content) +
    faq +
    `</article>`
  );
}

const KIND = {
  blog: { label: "Blog", base: "/blog" },
  compare: { label: "Compare", base: "/compare" },
  "use-cases": { label: "Use cases", base: "/use-cases" },
};

/** Build the list of pages to prerender: { path, title, description, image, type, schemas }. */
function pages() {
  const out = [];

  // Static pages.
  for (const [path, meta] of Object.entries(PAGE_META)) {
    const schemas = [];
    if (meta.schema?.includes("software")) schemas.push(softwareApplicationSchema());
    if (meta.schema?.includes("faq")) {
      const faqs = path === "/pricing" ? PRICING_FAQS : SITE_FAQS;
      schemas.push(faqPageSchema(faqs));
    }
    if (path !== "/") {
      const name = meta.title.replace(/ — InvoiceParsed$/, "").split(" — ")[0];
      schemas.push(breadcrumbSchema([{ name: "Home", path: "/" }, { name, path }]));
    }
    out.push({
      path,
      title: meta.titleRaw ? meta.title : `${meta.title} — ${SITE.name}`,
      description: meta.description,
      image: SITE.ogImage,
      type: "website",
      schemas,
    });
  }

  // Article-style pages (blog / compare / use-cases).
  const articles = [
    ...BLOG_POSTS.map((p) => ({ ...p, kind: "blog" })),
    ...COMPARISONS.map((p) => ({ ...p, kind: "compare" })),
    ...USE_CASES.map((p) => ({ ...p, kind: "use-cases" })),
  ];
  for (const post of articles) {
    const meta = KIND[post.kind];
    const path = `${meta.base}/${post.slug}`;
    const crumbs = [
      { name: "Home", path: "/" },
      { name: meta.label, path: meta.base },
      { name: post.title, path },
    ];
    const schemas = [
      articleSchema({
        title: post.title,
        description: post.description,
        url: path,
        image: post.image,
        author: post.author,
        datePublished: post.datePublished,
        dateModified: post.dateModified,
      }),
      breadcrumbSchema(crumbs),
    ];
    if (post.faqs?.length) schemas.push(faqPageSchema(post.faqs));
    out.push({
      path,
      title: `${post.title} — ${SITE.name}`,
      description: post.description,
      image: post.image || SITE.ogImage,
      type: "article",
      schemas,
      bodyHtml: articleHtml(post),
    });
  }
  return out;
}

function headBlock({ path, title, description, image, type }) {
  const metaTitle = clamp(title, 60);
  const desc = clamp(description, 155);
  const canonical = absoluteUrl(path);
  const img = absoluteUrl(image);
  return [
    `<title>${esc(title)}</title>`,
    `<meta name="description" content="${esc(desc)}" />`,
    `<meta name="robots" content="index,follow,max-image-preview:large" />`,
    `<link rel="canonical" href="${canonical}" />`,
    `<meta property="og:site_name" content="${esc(SITE.name)}" />`,
    `<meta property="og:type" content="${type}" />`,
    `<meta property="og:title" content="${esc(metaTitle)}" />`,
    `<meta property="og:description" content="${esc(desc)}" />`,
    `<meta property="og:url" content="${canonical}" />`,
    `<meta property="og:image" content="${img}" />`,
    `<meta name="twitter:card" content="summary_large_image" />`,
    `<meta name="twitter:site" content="${esc(SITE.twitter)}" />`,
    `<meta name="twitter:title" content="${esc(metaTitle)}" />`,
    `<meta name="twitter:description" content="${esc(desc)}" />`,
    `<meta name="twitter:image" content="${img}" />`,
  ].join("\n    ");
}

const SEO_BLOCK = /<!-- SEO:START[\s\S]*?<!-- SEO:END -->/;

function render(page) {
  if (!SEO_BLOCK.test(template)) {
    throw new Error("SEO:START/SEO:END markers not found in dist/index.html");
  }
  let html = template.replace(SEO_BLOCK, headBlock(page));
  const ld = page.schemas
    .map((s) => `<script type="application/ld+json">${JSON.stringify(s)}</script>`)
    .join("\n    ");
  if (ld) html = html.replace("</head>", `    ${ld}\n  </head>`);
  // Inject crawler-visible article content into the SPA mount point. React
  // (createRoot) replaces it on hydration, so users still get the full app.
  if (page.bodyHtml) {
    html = html.replace('<div id="root"></div>', `<div id="root">${page.bodyHtml}</div>`);
  }
  return html;
}

let count = 0;
for (const page of pages()) {
  const html = render(page);
  // Flat files (/pricing.html, /blog/<slug>.html) — served without a
  // trailing-slash redirect, so the served URL matches the canonical exactly.
  const file =
    page.path === "/"
      ? resolve(DIST, "index.html")
      : resolve(DIST, page.path.replace(/^\//, "") + ".html");
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, html, "utf8");
  count++;
}
console.log(`✓ prerendered ${count} routes with per-route <head> + JSON-LD`);
