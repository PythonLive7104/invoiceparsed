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
import { HERO, ANSWER, STATS, FEATURES, STEPS, AUDIENCES } from "../src/content/home.js";
import { PLANS, PLAN_ORDER } from "../src/lib/plans.js";
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
  organizationSchema,
  websiteSchema,
} from "../src/lib/schema.js";

// Site-wide entity schema, emitted into every page's <head> so AI engines and
// no-JS crawlers always see the Organization (+ sameAs) and WebSite entities.
const SITE_SCHEMAS = [organizationSchema(), websiteSchema()];

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

/** A crawler-visible FAQ block (also helps AEO / featured snippets). */
function faqHtml(faqs) {
  if (!faqs?.length) return "";
  return (
    `<section><h2>Frequently asked questions</h2>` +
    faqs.map((f) => `<h3>${esc(f.q)}</h3><p>${esc(f.a)}</p>`).join("") +
    `</section>`
  );
}

/** Crawler-visible pricing block — real plan names, prices and what each adds. */
function pricingHtml() {
  return (
    `<section><h2>Pricing</h2><ul>` +
    PLAN_ORDER.map((id) => {
      const p = PLANS[id];
      const price = p.price === 0 ? "Free" : `$${p.price}/mo`;
      return `<li><strong>${esc(p.name)} — ${esc(price)}</strong>. ${esc(p.tagline)} ` +
        `Includes: ${esc(p.features.join("; "))}.</li>`;
    }).join("") +
    `</ul></section>`
  );
}

/** Full crawler-visible homepage body (hero, answer, features, steps, FAQ). */
function homeBodyHtml() {
  const title = HERO.title.lead + HERO.title.highlight + HERO.title.tail;
  const stats = `<ul>${STATS.map(([v, l]) => `<li><strong>${esc(v)}</strong> — ${esc(l)}</li>`).join("")}</ul>`;
  const features =
    `<section><h2>Built to kill manual data entry</h2>` +
    FEATURES.map((f) => `<div><h3>${esc(f.title)}</h3><p>${esc(f.desc)}</p></div>`).join("") +
    `</section>`;
  const steps =
    `<section><h2>From file to data in three steps</h2>` +
    STEPS.map((s, i) => `<div><h3>Step ${i + 1}: ${esc(s.title)}</h3><p>${esc(s.desc)}</p></div>`).join("") +
    `</section>`;
  const audiences =
    `<section><h2>From solo freelancers to finance teams</h2>` +
    AUDIENCES.map((a) =>
      `<div><h3>${esc(a.title)}</h3><p>${esc(a.desc)}</p>` +
      `<ul>${a.points.map((p) => `<li>${esc(p)}</li>`).join("")}</ul></div>`,
    ).join("") +
    `</section>`;
  return (
    `<header><p>${esc(HERO.eyebrow)}</p><h1>${esc(title)}</h1>` +
    `<p>${esc(HERO.subhead)}</p>` +
    `<p><a href="${HERO.primaryCta.to}">${esc(HERO.primaryCta.label)}</a></p></header>` +
    `<p>${esc(ANSWER)}</p>` +
    stats + features + steps + audiences + pricingHtml() + faqHtml(SITE_FAQS)
  );
}

// Index pages list their child articles, giving crawlers real internal links.
const INDEX_ITEMS = {
  "/blog": { items: BLOG_POSTS, base: "/blog" },
  "/compare": { items: COMPARISONS, base: "/compare" },
  "/use-cases": { items: USE_CASES, base: "/use-cases" },
};

function indexLinksHtml(path) {
  const cfg = INDEX_ITEMS[path];
  if (!cfg) return "";
  return (
    `<ul>` +
    cfg.items
      .map(
        (p) =>
          `<li><a href="${cfg.base}/${p.slug}">${esc(p.title)}</a>` +
          (p.description ? ` — ${esc(p.description)}` : "") +
          `</li>`,
      )
      .join("") +
    `</ul>`
  );
}

/** Baseline crawler-visible body for a static page: H1 + intro (+ pricing/links/FAQ). */
function staticBodyHtml(path, page, faqs) {
  const heading = page.title.replace(new RegExp(` — ${SITE.name}$`), "").split(" — ")[0];
  return (
    `<h1>${esc(heading)}</h1><p>${esc(page.description)}</p>` +
    (path === "/pricing" ? pricingHtml() : "") +
    indexLinksHtml(path) +
    faqHtml(faqs)
  );
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
    const faqs = meta.schema?.includes("faq")
      ? (path === "/pricing" ? PRICING_FAQS : SITE_FAQS)
      : null;
    if (meta.schema?.includes("software")) schemas.push(softwareApplicationSchema());
    if (faqs) schemas.push(faqPageSchema(faqs));
    if (path !== "/") {
      const name = meta.title.replace(/ — InvoiceParsed$/, "").split(" — ")[0];
      schemas.push(breadcrumbSchema([{ name: "Home", path: "/" }, { name, path }]));
    }
    const page = {
      path,
      title: meta.titleRaw ? meta.title : `${meta.title} — ${SITE.name}`,
      description: meta.description,
      image: SITE.ogImage,
      type: "website",
      schemas,
    };
    // Crawler-visible body so non-JS bots see real content, not an empty #root.
    page.bodyHtml = path === "/" ? homeBodyHtml() : staticBodyHtml(path, page, faqs);
    out.push(page);
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
  const ld = [...SITE_SCHEMAS, ...page.schemas]
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
