import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Upload,
  ScanLine,
  FileJson,
  Check,
  Code2,
  ShieldCheck,
  Layers,
  Gauge,
  Clock,
  Receipt,
  ArrowRight,
  User,
  Building2,
} from "lucide-react";
import { MarketingNav } from "@/components/marketing/MarketingNav";
import { Hero } from "@/components/marketing/Hero";
import { Footer } from "@/components/marketing/Footer";
import { Reveal } from "@/components/ui/Reveal";
import { Button } from "@/components/ui/Button";
import { SEO } from "@/components/seo/SEO";
import { JsonLd } from "@/components/seo/JsonLd";
import { FaqSection } from "@/components/seo/FaqSection";
import { softwareApplicationSchema } from "@/lib/schema";
import { SITE_FAQS } from "@/content/registry";
import { PAGE_META } from "@/content/pages";
import { PLANS, plansForSegment } from "@/lib/plans";
import { cn } from "@/lib/utils";

const audiences = [
  {
    id: "personal",
    icon: User,
    eyebrow: "For individuals",
    title: "Freelancers & sole traders",
    desc: "Stop logging client invoices into a spreadsheet by hand. Drag in a PDF, get clean data and a CSV in seconds — and reclaim hours every week.",
    points: ["Simple drag & drop", "CSV export for your books", "Accurate line-item capture", "Starts free"],
  },
  {
    id: "business",
    icon: Building2,
    eyebrow: "For businesses",
    title: "Teams, agencies & finance ops",
    desc: "Process invoices at volume and feed them straight into your accounting stack. Batch upload, REST API, webhooks and centralized billing.",
    points: ["Batch & multi-page", "REST API + webhooks", "High-volume processing", "Centralized billing"],
  },
];

const features = [
  { icon: ScanLine, title: "Field-perfect extraction", desc: "Vendor, invoice number, dates, line items, subtotal, tax and total — every field, captured accurately." },
  { icon: Layers, title: "PDF & image, any layout", desc: "Upload PDFs or photos. Handles messy scans, multi-page invoices and unusual layouts." },
  { icon: FileJson, title: "QuickBooks-compatible export", desc: "One click to a strict JSON payload or a QuickBooks-compatible CSV that maps straight into your accounting software." },
  { icon: Gauge, title: "95%+ accuracy", desc: "Tuned prompts and structured outputs keep extraction reliable on standard invoice formats." },
  { icon: Clock, title: "Seconds, not hours", desc: "What took a bookkeeper 6 hours a week now happens the moment you drop a file." },
  { icon: ShieldCheck, title: "Private by design", desc: "Your documents are processed for extraction only — no training, no resale of your data." },
];

const steps = [
  { icon: Upload, title: "Upload", desc: "Drag & drop a PDF or image, or pick a file. Up to 10MB per invoice." },
  { icon: ScanLine, title: "Extract", desc: "Our AI reads the document and structures every field in seconds." },
  { icon: FileJson, title: "Export", desc: "Review, edit, then download JSON or CSV — or pull it via the API." },
];

export default function Landing() {
  const [segment, setSegment] = useState("personal");
  const planIds = plansForSegment(segment);

  return (
    <main className="relative">
      <SEO title={PAGE_META["/"].title} description={PAGE_META["/"].description} path="/" />
      <JsonLd data={softwareApplicationSchema()} />

      <MarketingNav />
      <Hero />

      {/* Answer-first paragraph for AEO — visually subtle, crawler-visible. */}
      <p className="container-page -mt-2 max-w-3xl pb-2 text-base leading-relaxed text-slate-400">
        InvoiceParsed is an AI-powered invoice and receipt data extraction tool
        that turns invoice or receipt PDFs and images into structured data —
        vendor, line items, tax and totals — in seconds. Upload a file and export
        a QuickBooks-compatible CSV or JSON, with a confidence score on every
        field. No templates, no manual data entry.
      </p>

      <section className="border-y border-white/[0.06] bg-white/[0.015] py-8">
        <div className="container-page grid grid-cols-2 gap-6 text-center sm:grid-cols-4">
          {[
            ["5 sec", "Avg. processing"],
            ["95%+", "Field accuracy"],
            ["10+", "Fields per invoice"],
            ["JSON/CSV", "Export formats"],
          ].map(([stat, label]) => (
            <div key={label}>
              <div className="text-2xl font-semibold text-white sm:text-3xl">{stat}</div>
              <div className="mt-1 text-xs text-slate-500 sm:text-sm">{label}</div>
            </div>
          ))}
        </div>
      </section>

      <section id="features" className="relative py-24 sm:py-32">
        <div className="container-page">
          <Reveal className="mx-auto max-w-2xl text-center">
            <span className="text-sm font-semibold text-brand-400">Everything you need</span>
            <h2 className="mt-3 text-balance text-4xl font-semibold tracking-tight text-white sm:text-5xl">
              Built to kill manual data entry
            </h2>
            <p className="mt-4 text-lg text-slate-400">
              InvoiceParsed does one thing exceptionally well: it reads invoices and hands you clean,
              structured data.
            </p>
          </Reveal>

          <div className="mt-16 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {features.map((f, i) => (
              <Reveal key={f.title} delay={i * 0.05}>
                <div className="group glass h-full rounded-2xl p-6 transition-all duration-300 hover:-translate-y-1 hover:border-brand-400/30">
                  <div className="grid h-11 w-11 place-items-center rounded-xl bg-brand-500/10 text-brand-300 ring-1 ring-inset ring-brand-400/20 transition-colors group-hover:bg-brand-500/20">
                    <f.icon size={20} />
                  </div>
                  <h3 className="mt-5 text-lg font-semibold text-white">{f.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-slate-400">{f.desc}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* Who it's for — B2C + B2B */}
      <section id="who" className="relative py-20 sm:py-24">
        <div className="container-page">
          <Reveal className="mx-auto max-w-2xl text-center">
            <span className="text-sm font-semibold text-brand-400">Built for both</span>
            <h2 className="mt-3 text-balance text-4xl font-semibold tracking-tight text-white sm:text-5xl">
              From solo freelancers to finance teams
            </h2>
          </Reveal>

          <div className="mt-14 grid gap-6 lg:grid-cols-2">
            {audiences.map((a, i) => (
              <Reveal key={a.id} delay={i * 0.08}>
                <div className="glass h-full rounded-2xl p-8">
                  <div className="flex items-center gap-3">
                    <span className="grid h-11 w-11 place-items-center rounded-xl bg-brand-gradient text-white shadow-glow-sm">
                      <a.icon size={20} />
                    </span>
                    <span className="text-sm font-semibold text-brand-300">{a.eyebrow}</span>
                  </div>
                  <h3 className="mt-5 text-2xl font-semibold text-white">{a.title}</h3>
                  <p className="mt-3 text-slate-400">{a.desc}</p>
                  <ul className="mt-6 grid grid-cols-2 gap-3">
                    {a.points.map((p) => (
                      <li key={p} className="flex items-start gap-2 text-sm text-slate-300">
                        <Check size={16} className="mt-0.5 shrink-0 text-brand-400" />
                        {p}
                      </li>
                    ))}
                  </ul>
                  <div className="mt-7">
                    <Button
                      to="/signup"
                      variant={a.id === "business" ? "primary" : "secondary"}
                      onClick={() => setSegment(a.id)}
                    >
                      {a.id === "business" ? "Talk to us / start free" : "Start free"}
                      <ArrowRight size={16} />
                    </Button>
                  </div>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <section id="how" className="relative py-24 sm:py-28">
        <div className="container-page">
          <Reveal className="mx-auto max-w-2xl text-center">
            <span className="text-sm font-semibold text-brand-400">How it works</span>
            <h2 className="mt-3 text-balance text-4xl font-semibold tracking-tight text-white sm:text-5xl">
              From file to data in three steps
            </h2>
          </Reveal>

          <div className="relative mt-16 grid gap-6 md:grid-cols-3">
            <div className="pointer-events-none absolute left-0 right-0 top-12 hidden h-px bg-gradient-to-r from-transparent via-brand-500/40 to-transparent md:block" />
            {steps.map((s, i) => (
              <Reveal key={s.title} delay={i * 0.1}>
                <div className="glass relative h-full rounded-2xl p-7 text-center">
                  <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-brand-gradient text-white shadow-glow-sm">
                    <s.icon size={24} />
                  </div>
                  <div className="mt-5 text-xs font-semibold uppercase tracking-wider text-brand-400">
                    Step {i + 1}
                  </div>
                  <h3 className="mt-1 text-xl font-semibold text-white">{s.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-slate-400">{s.desc}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <section id="api" className="relative py-24 sm:py-28">
        <div className="container-page">
          <div className="glass gradient-border overflow-hidden rounded-3xl">
            <div className="grid items-center gap-10 p-8 sm:p-12 lg:grid-cols-2">
              <Reveal>
                <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-xs font-medium text-accent-cyan">
                  <Code2 size={14} /> Developer-first
                </span>
                <h2 className="mt-4 text-balance text-3xl font-semibold tracking-tight text-white sm:text-4xl">
                  A REST API that just returns clean invoices
                </h2>
                <p className="mt-4 text-slate-400">
                  POST a file, get structured JSON back. Wire InvoiceParsed into your accounting
                  workflow, ERP, or internal tools. Available on the Pro plan.
                </p>
                <div className="mt-7">
                  <Button to="/signup" variant="secondary">
                    Get API access <ArrowRight size={16} />
                  </Button>
                </div>
              </Reveal>

              <Reveal delay={0.1}>
                <div className="overflow-hidden rounded-2xl border border-white/10 bg-ink-950/80">
                  <div className="flex items-center gap-1.5 border-b border-white/[0.06] px-4 py-2.5">
                    <span className="h-2.5 w-2.5 rounded-full bg-red-400/70" />
                    <span className="h-2.5 w-2.5 rounded-full bg-amber-400/70" />
                    <span className="h-2.5 w-2.5 rounded-full bg-emerald-400/70" />
                    <span className="ml-2 text-[11px] text-slate-500">Terminal</span>
                  </div>
                  <pre className="overflow-x-auto whitespace-pre-wrap break-words p-5 font-mono text-[12px] leading-relaxed text-slate-300 sm:text-[12.5px]">
                    <span className="text-slate-500"># Extract an invoice</span>
                    {"\n"}
                    <span className="text-accent-violet">curl</span> -X POST
                    https://api.invoiceparsed.com/extract{" \\"}
                    {"\n  "}-H{" "}
                    <span className="text-emerald-300">"Authorization: Bearer $KEY"</span>
                    {" \\"}
                    {"\n  "}-F <span className="text-emerald-300">"file=@invoice.pdf"</span>
                    {"\n\n"}
                    <span className="text-slate-500"># → 200 OK</span>
                    {"\n"}
                    <span className="text-accent-cyan">
                      {'{ "vendor": {…}, "total": 1620.00 }'}
                    </span>
                  </pre>
                </div>
              </Reveal>
            </div>
          </div>
        </div>
      </section>

      <section id="pricing" className="relative py-24 sm:py-32">
        <div className="container-page">
          <Reveal className="mx-auto max-w-2xl text-center">
            <span className="text-sm font-semibold text-brand-400">Pricing</span>
            <h2 className="mt-3 text-balance text-4xl font-semibold tracking-tight text-white sm:text-5xl">
              Simple, volume-based pricing
            </h2>
            <p className="mt-4 text-lg text-slate-400">
              Start free. Upgrade when invoices pile up. Cancel anytime.
            </p>

            {/* Audience toggle: Individuals (B2C) / Businesses (B2B) */}
            <div className="mt-8 inline-flex rounded-full border border-white/10 bg-white/[0.03] p-1">
              {[
                { id: "personal", label: "For individuals", icon: User },
                { id: "business", label: "For businesses", icon: Building2 },
              ].map((t) => (
                <button
                  key={t.id}
                  onClick={() => setSegment(t.id)}
                  className={cn(
                    "inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition-all",
                    segment === t.id
                      ? "bg-brand-gradient text-white shadow-glow-sm"
                      : "text-slate-400 hover:text-white",
                  )}
                >
                  <t.icon size={15} /> {t.label}
                </button>
              ))}
            </div>
          </Reveal>

          <div
            className={cn(
              "mt-12 grid items-stretch gap-6",
              planIds.length >= 3 ? "lg:grid-cols-3" : "sm:grid-cols-2 lg:mx-auto lg:max-w-3xl",
            )}
          >
            {planIds.map((id, i) => {
              const plan = PLANS[id];
              const featured = plan.highlighted || (segment === "business" && id === "business");
              return (
                <Reveal key={id} delay={i * 0.08}>
                  <div
                    className={cn(
                      "relative flex h-full flex-col rounded-2xl p-7",
                      featured ? "gradient-border bg-white/[0.04] shadow-glow" : "glass",
                    )}
                  >
                    {featured && (
                      <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-brand-gradient px-3 py-1 text-xs font-semibold text-white shadow-glow-sm">
                        {segment === "business" && id === "business" ? "Best for teams" : "Most popular"}
                      </span>
                    )}
                    <div className="flex items-center gap-2">
                      <Receipt size={18} className="text-brand-300" />
                      <h3 className="text-lg font-semibold text-white">{plan.name}</h3>
                    </div>
                    <div className="mt-4 flex items-end gap-1">
                      <span className="text-5xl font-semibold tracking-tight text-white">
                        ${plan.price}
                      </span>
                      <span className="mb-1.5 text-sm text-slate-500">/mo</span>
                    </div>
                    <p className="mt-2 text-sm text-slate-400">{plan.tagline}</p>

                    <ul className="mt-6 space-y-3">
                      {plan.features.map((feat) => (
                        <li key={feat} className="flex items-start gap-2.5 text-sm text-slate-300">
                          <Check size={17} className="mt-0.5 shrink-0 text-brand-400" />
                          {feat}
                        </li>
                      ))}
                    </ul>

                    <div className="mt-8 pt-2">
                      <Button
                        to="/signup"
                        variant={featured ? "primary" : "secondary"}
                        className="w-full"
                      >
                        {plan.price === 0 ? "Start free" : `Choose ${plan.name}`}
                      </Button>
                    </div>
                  </div>
                </Reveal>
              );
            })}
          </div>
        </div>
      </section>

      <section className="relative py-20">
        <div className="container-page">
          <Reveal className="glass relative overflow-hidden rounded-3xl px-8 py-16 text-center sm:px-16">
            <div className="pointer-events-none absolute -top-24 left-1/2 h-72 w-[640px] -translate-x-1/2 rounded-full bg-radial-glow blur-2xl" />
            <h2 className="relative text-balance text-4xl font-semibold tracking-tight text-white sm:text-5xl">
              Stop typing invoices. Start shipping.
            </h2>
            <p className="relative mx-auto mt-4 max-w-xl text-lg text-slate-400">
              Join freelancers and small businesses reclaiming hours every week. Your first 5
              invoices are on us.
            </p>
            <div className="relative mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Button to="/signup" size="lg">
                Get started free <ArrowRight size={18} />
              </Button>
              <Link to="/login" className="text-sm text-slate-400 hover:text-white">
                or sign in →
              </Link>
            </div>
          </Reveal>
        </div>
      </section>

      <section className="container-page py-16 sm:py-20">
        <FaqSection faqs={SITE_FAQS} />
      </section>

      <Footer />
    </main>
  );
}
