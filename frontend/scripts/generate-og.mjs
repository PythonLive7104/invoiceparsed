// Generates per-post Open Graph images (1200x630) for every blog post, matching
// the brand card design (dark ink card, violet accent bar, InvoiceParsed
// wordmark, big title, muted category footer).
//
// Output: public/og/blog/<slug>.png — one per BLOG_POSTS entry.
//
// Run: node scripts/generate-og.mjs
// Requires `sharp`. If sharp isn't installed in node_modules (peer-dep
// conflicts in this repo), point SHARP_PATH at an install elsewhere, e.g.:
//   SHARP_PATH=/tmp/x/node_modules/sharp node scripts/generate-og.mjs

import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { mkdir, writeFile } from "node:fs/promises";
import { BLOG_POSTS } from "../src/content/registry.js";

const require = createRequire(import.meta.url);
const sharp = require(process.env.SHARP_PATH || "sharp");

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT_DIR = resolve(__dirname, "../public/og/blog");

const W = 1200;
const H = 630;
const ACR = { ocr: "OCR", api: "API", pdf: "PDF", csv: "CSV", ai: "AI" };
const SMALL = new Set(["to", "for", "a", "an", "the", "and", "of", "in", "on", "vs"]);

const esc = (s) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

function titleCase(s) {
  return s
    .split(/\s+/)
    .map((w, i) => {
      const lw = w.toLowerCase();
      if (ACR[lw]) return ACR[lw];
      if (i > 0 && SMALL.has(lw)) return lw;
      return w.charAt(0).toUpperCase() + w.slice(1);
    })
    .join(" ");
}

// Split "Title text (Parenthetical)" -> { base, paren }.
function splitParen(title) {
  const m = title.match(/^(.*?)\s*\(([^)]+)\)\s*$/);
  return m ? { base: m[1].trim(), paren: m[2].trim() } : { base: title.trim(), paren: null };
}

// Greedy word-wrap using an estimated glyph width for Inter ExtraBold.
function wrap(text, fontSize, maxWidth) {
  const charW = fontSize * 0.58;
  const maxChars = Math.max(8, Math.floor(maxWidth / charW));
  const words = text.split(/\s+/);
  const lines = [];
  let line = "";
  for (const word of words) {
    const next = line ? `${line} ${word}` : word;
    if (next.length > maxChars && line) {
      lines.push(line);
      line = word;
    } else {
      line = next;
    }
  }
  if (line) lines.push(line);
  return lines;
}

function svgFor(post) {
  const { base, paren } = splitParen(post.title);
  let eyebrow = paren && !/^\d{4}$/.test(paren) ? paren : titleCase(post.tags?.[0] || "Guide");

  // Fit the title into at most 3 lines, shrinking the font if needed.
  const maxTextWidth = 980;
  let fontSize = 72;
  let lines = wrap(base, fontSize, maxTextWidth);
  if (lines.length > 3) {
    fontSize = 60;
    lines = wrap(base, fontSize, maxTextWidth);
  }
  if (lines.length > 3) {
    fontSize = 52;
    lines = wrap(base, fontSize, maxTextWidth).slice(0, 3);
  }

  const lineHeight = fontSize * 1.14;
  const blockH = lineHeight * lines.length;
  const startY = (H - blockH) / 2 + fontSize * 0.78; // vertically center the title block
  const x = 96;

  const tspans = lines
    .map((ln, i) => `<tspan x="${x}" y="${(startY + i * lineHeight).toFixed(1)}">${esc(ln)}</tspan>`)
    .join("");

  return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="accent" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#818cf8"/>
      <stop offset="0.6" stop-color="#6366f1"/>
      <stop offset="1" stop-color="#a855f7"/>
    </linearGradient>
    <radialGradient id="glow" cx="0.5" cy="0" r="0.8">
      <stop offset="0" stop-color="#6366f1" stop-opacity="0.18"/>
      <stop offset="1" stop-color="#6366f1" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="${W}" height="${H}" fill="#070a13"/>
  <rect x="24" y="24" width="${W - 48}" height="${H - 48}" rx="28" fill="#0b0f1a" stroke="#ffffff" stroke-opacity="0.06" stroke-width="1.5"/>
  <rect x="24" y="24" width="${W - 48}" height="320" rx="28" fill="url(#glow)"/>
  <rect x="56" y="70" width="8" height="490" rx="4" fill="url(#accent)"/>
  <text font-family="Inter" font-weight="800" font-size="40" x="${x}" y="158">
    <tspan fill="#ffffff">Invoice</tspan><tspan fill="#818cf8">Parsed</tspan>
  </text>
  <text font-family="Inter" font-weight="800" font-size="${fontSize}" fill="#ffffff" letter-spacing="-1.2">${tspans}</text>
  <text font-family="Inter" font-weight="600" font-size="28" fill="#64748b" x="${x}" y="556">${esc(eyebrow)} · InvoiceParsed</text>
</svg>`;
}

async function main() {
  await mkdir(OUT_DIR, { recursive: true });
  for (const post of BLOG_POSTS) {
    const svg = svgFor(post);
    const out = resolve(OUT_DIR, `${post.slug}.png`);
    await sharp(Buffer.from(svg)).png().toFile(out);
    console.log("✓", `og/blog/${post.slug}.png`);
  }
  console.log(`\nGenerated ${BLOG_POSTS.length} OG images in public/og/blog/`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
