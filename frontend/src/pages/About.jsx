import { Link } from "react-router-dom";
import { MarketingNav } from "@/components/marketing/MarketingNav";
import { Footer } from "@/components/marketing/Footer";
import { Button } from "@/components/ui/Button";
import { SEO } from "@/components/seo/SEO";
import { JsonLd } from "@/components/seo/JsonLd";
import { breadcrumbSchema } from "@/lib/schema";
import { PAGE_META } from "@/content/pages";

export default function About() {
  const meta = PAGE_META["/about"];
  return (
    <div className="min-h-screen bg-ink-950">
      <SEO title={meta.title} description={meta.description} path="/about" />
      <JsonLd data={breadcrumbSchema([{ name: "Home", path: "/" }, { name: "About", path: "/about" }])} />
      <MarketingNav />

      <main className="mx-auto w-full max-w-3xl px-5 pb-20 pt-28">
        <h1 className="text-3xl font-semibold tracking-tight text-white sm:text-4xl">
          About InvoiceParsed
        </h1>
        {/* Answer-first paragraph (AEO) */}
        <p className="mt-6 text-lg leading-relaxed text-slate-200">
          InvoiceParsed is an AI-powered invoice data extraction tool built to end
          manual invoice data entry for freelancers and small businesses. We turn
          invoice PDFs and images into clean, structured data — vendor, line items,
          tax and totals — in seconds.
        </p>

        <div className="mt-8 space-y-5 text-base leading-relaxed text-slate-300">
          <h2 className="text-xl font-semibold text-white">Our mission</h2>
          <p>
            Bookkeeping shouldn't mean retyping numbers off a PDF. We believe small
            teams deserve the same automation that large enterprises buy expensive
            software for — without the setup, templates or per-vendor configuration.
          </p>
          <h2 className="text-xl font-semibold text-white">How it works</h2>
          <p>
            InvoiceParsed uses modern AI vision models that understand invoice
            layouts, so extraction works across formats and even on scans and
            photos. Every field comes back with a confidence score, and you can
            export to JSON or CSV or push data through our REST API and webhooks.
          </p>
          <h2 className="text-xl font-semibold text-white">Who it's for</h2>
          <p>
            From solo freelancers logging client invoices to finance teams
            processing supplier invoices at volume, InvoiceParsed scales from a free
            plan to high-volume Business usage.
          </p>
        </div>

        <div className="mt-12 flex flex-wrap items-center gap-4">
          <Button to="/signup">Start free</Button>
          <Link to="/pricing" className="text-sm text-slate-400 hover:text-white">
            See pricing →
          </Link>
        </div>
      </main>
      <Footer />
    </div>
  );
}
