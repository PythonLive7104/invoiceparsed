/**
 * Build-time sitemap generator. Reads the content registry (the same module the
 * app uses) and writes public/sitemap.xml, so every static + dynamic route is
 * included automatically. Wired into `npm run build`.
 *
 *   node scripts/generate-sitemap.mjs
 */
import { writeFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { SITE } from "../src/content/site.js";
import { allRoutes } from "../src/content/registry.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(__dirname, "../public/sitemap.xml");

const today = new Date().toISOString().slice(0, 10);

function urlEntry({ path, changefreq, priority, lastmod }) {
  const loc = `${SITE.url}${path === "/" ? "/" : path}`;
  return [
    "  <url>",
    `    <loc>${loc}</loc>`,
    `    <lastmod>${lastmod || today}</lastmod>`,
    changefreq ? `    <changefreq>${changefreq}</changefreq>` : "",
    priority != null ? `    <priority>${priority.toFixed(1)}</priority>` : "",
    "  </url>",
  ]
    .filter(Boolean)
    .join("\n");
}

const xml = [
  '<?xml version="1.0" encoding="UTF-8"?>',
  '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
  ...allRoutes().map(urlEntry),
  "</urlset>",
  "",
].join("\n");

mkdirSync(dirname(OUT), { recursive: true });
writeFileSync(OUT, xml, "utf8");
console.log(`✓ sitemap.xml written with ${allRoutes().length} URLs → ${OUT}`);
