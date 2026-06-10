import { Link } from "react-router-dom";
import { Terminal, KeyRound, Webhook, ShieldCheck } from "lucide-react";
import { MarketingNav } from "@/components/marketing/MarketingNav";
import { Footer } from "@/components/marketing/Footer";
import { Button } from "@/components/ui/Button";
import { SEO } from "@/components/seo/SEO";
import { JsonLd } from "@/components/seo/JsonLd";
import { breadcrumbSchema } from "@/lib/schema";
import { ApiQuickStart } from "@/components/api/ApiQuickStart";
import { SITE } from "@/content/site";
import { PAGE_META } from "@/content/pages";

const BASE = typeof window !== "undefined" ? window.location.origin : SITE.url;

const ENDPOINTS = [
  ["POST", "/api/extract", "Extract a document (multipart file + doc_type)"],
  ["GET", "/api/extractions", "List your extractions"],
  ["GET", "/api/extractions/{id}", "Get a single extraction"],
  ["GET", "/api/extractions/{id}/csv", "Download as CSV"],
  ["GET", "/api/extractions/{id}/xlsx", "Download as Excel"],
  ["DELETE", "/api/extractions/{id}", "Delete an extraction"],
];

function H2({ id, children }) {
  return <h2 id={id} className="mt-12 text-xl font-semibold text-white sm:text-2xl">{children}</h2>;
}

export default function ApiDocs() {
  const meta = PAGE_META["/docs"];
  return (
    <div className="min-h-screen bg-ink-950">
      <SEO title={meta.title} titleRaw={meta.titleRaw} description={meta.description} path="/docs" />
      <JsonLd data={breadcrumbSchema([{ name: "Home", path: "/" }, { name: "API docs", path: "/docs" }])} />
      <MarketingNav />

      <main className="mx-auto w-full max-w-3xl px-5 pb-24 pt-28">
        <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs font-medium text-accent-cyan">
          <Terminal size={14} /> Developer docs
        </span>
        <h1 className="mt-5 text-3xl font-semibold tracking-tight text-white sm:text-4xl">
          InvoiceParsed API
        </h1>
        {/* Answer-first (AEO) */}
        <p className="mt-4 text-lg leading-relaxed text-slate-200">
          The InvoiceParsed REST API extracts structured data from invoices, receipts and bank
          statements. POST a PDF or image to <code className="rounded bg-white/[0.06] px-1.5 py-0.5 font-mono text-base">/api/extract</code>{" "}
          and get clean JSON back — vendor, line items, tax and totals — with a confidence score on
          every field. API access is available on the Pro and Business plans.
        </p>

        <H2 id="base-url">Base URL</H2>
        <pre className="mt-3 overflow-x-auto rounded-xl border border-white/10 bg-ink-950/70 p-4 font-mono text-sm text-slate-300">{BASE}</pre>

        <H2 id="auth">Authentication</H2>
        <p className="mt-3 text-slate-300">
          Create an API key in your dashboard (API &amp; Webhooks) and send it on every request as a
          Bearer token or an <code className="rounded bg-white/[0.06] px-1.5 py-0.5 font-mono text-sm">X-API-Key</code> header.
          Keys look like <code className="rounded bg-white/[0.06] px-1.5 py-0.5 font-mono text-sm">ip_live_…</code> — keep them secret.
        </p>
        <pre className="mt-3 overflow-x-auto rounded-xl border border-white/10 bg-ink-950/70 p-4 font-mono text-sm text-slate-300">{`Authorization: Bearer ip_live_...
# or
X-API-Key: ip_live_...`}</pre>

        <H2 id="quick-start">Quick start</H2>
        <p className="mt-3 text-slate-300">
          Send a file with <code className="rounded bg-white/[0.06] px-1.5 py-0.5 font-mono text-sm">doc_type</code> set to{" "}
          <code className="rounded bg-white/[0.06] px-1.5 py-0.5 font-mono text-sm">invoice</code>,{" "}
          <code className="rounded bg-white/[0.06] px-1.5 py-0.5 font-mono text-sm">receipt</code> or{" "}
          <code className="rounded bg-white/[0.06] px-1.5 py-0.5 font-mono text-sm">statement</code>.
        </p>
        <div className="mt-4">
          <ApiQuickStart base={BASE} />
        </div>

        <H2 id="endpoints">Endpoints</H2>
        <div className="mt-3 overflow-hidden rounded-xl border border-white/10">
          <table className="w-full text-left text-sm">
            <thead className="bg-white/[0.03] text-xs uppercase tracking-wider text-slate-500">
              <tr>
                <th className="px-4 py-2.5 font-medium">Method</th>
                <th className="px-4 py-2.5 font-medium">Path</th>
                <th className="px-4 py-2.5 font-medium">Description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.05]">
              {ENDPOINTS.map(([m, p, d]) => (
                <tr key={p} className="text-slate-300">
                  <td className="px-4 py-2.5 font-mono text-xs text-brand-300">{m}</td>
                  <td className="px-4 py-2.5 font-mono text-xs">{p}</td>
                  <td className="px-4 py-2.5 text-slate-400">{d}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <H2 id="webhooks">Webhooks</H2>
        <p className="mt-3 text-slate-300">
          Register endpoints in your dashboard to receive an <code className="rounded bg-white/[0.06] px-1.5 py-0.5 font-mono text-sm">extraction.completed</code>{" "}
          POST when a document finishes. Each request is signed:
        </p>
        <div className="mt-3 flex items-start gap-2.5 rounded-xl border border-white/[0.07] bg-white/[0.02] p-4 text-sm text-slate-400">
          <ShieldCheck size={16} className="mt-0.5 shrink-0 text-brand-300" />
          <span>
            Verify <code className="rounded bg-white/[0.06] px-1 py-0.5 font-mono text-xs">X-InvoiceParsed-Signature: sha256=&lt;hmac&gt;</code>{" "}
            against your endpoint's signing secret using the raw request body. Failed deliveries retry with exponential backoff.
          </span>
        </div>

        <H2 id="limits">Files &amp; limits</H2>
        <ul className="mt-3 list-disc space-y-1.5 pl-5 text-slate-300 marker:text-brand-400">
          <li>Accepted: PDF, JPG, PNG up to 10MB each.</li>
          <li>Each completed extraction counts as one document toward your monthly limit.</li>
          <li>Requests are rate-limited per IP; over the limit returns HTTP 429.</li>
          <li>Bank statement extraction requires the Business plan.</li>
        </ul>

        <div className="mt-12 flex flex-wrap items-center gap-4 rounded-2xl border border-brand-400/20 bg-brand-500/[0.06] p-6">
          <div className="flex items-center gap-2.5 text-brand-100">
            <KeyRound size={18} />
            <span className="text-sm">Ready to build? Create a key in your dashboard.</span>
          </div>
          <div className="flex gap-2">
            <Button to="/signup" size="sm">Get API access</Button>
            <Button to="/pricing" size="sm" variant="secondary">See pricing</Button>
          </div>
        </div>
      </main>
      <Footer />
    </div>
  );
}
