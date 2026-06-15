import { Check } from "lucide-react";
import { MarketingNav } from "@/components/marketing/MarketingNav";
import { Footer } from "@/components/marketing/Footer";
import { Button } from "@/components/ui/Button";
import { SEO } from "@/components/seo/SEO";
import { FaqSection } from "@/components/seo/FaqSection";
import { PAGE_META } from "@/content/pages";
import { PRICING_FAQS } from "@/content/registry";
import { PLAN_ORDER, PLANS } from "@/lib/plans";
import { cn } from "@/lib/utils";

export default function Pricing() {
  const meta = PAGE_META["/pricing"];
  return (
    <div className="min-h-screen bg-ink-950">
      <SEO title={meta.title} titleRaw={meta.titleRaw} description={meta.description} path="/pricing" />
      <MarketingNav />

      <main className="mx-auto w-full max-w-6xl px-5 pb-20 pt-28">
        <header className="mx-auto max-w-2xl text-center">
          <h1 className="text-3xl font-semibold tracking-tight text-white sm:text-4xl">
            Simple, transparent pricing
          </h1>
          {/* Answer-first paragraph (AEO) */}
          <p className="mt-4 text-lg leading-relaxed text-slate-300">
            InvoiceParsed pricing starts free with 5 invoices per month. Paid plans
            — Starter ($19), Pro ($49) and Business ($99) — add batch upload,
            multi-page invoices, the REST API and webhooks as you scale.
          </p>
        </header>

        <div className="mt-14 grid items-stretch gap-5 sm:grid-cols-2 xl:grid-cols-4">
          {PLAN_ORDER.map((id) => {
            const plan = PLANS[id];
            return (
              <div
                key={id}
                className={cn(
                  "relative flex h-full flex-col rounded-2xl p-7",
                  plan.highlighted ? "gradient-border bg-white/[0.04]" : "glass",
                )}
              >
                {plan.highlighted && (
                  <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-brand-gradient px-3 py-1 text-xs font-semibold text-white shadow-glow-sm">
                    Most popular
                  </span>
                )}
                <h2 className="text-lg font-semibold text-white">{plan.name}</h2>
                <div className="mt-4 flex items-end gap-1">
                  <span className="text-4xl font-semibold tracking-tight text-white">${plan.price}</span>
                  <span className="mb-1.5 text-sm text-slate-500">/mo</span>
                </div>
                <p className="mt-2 text-sm text-slate-400">{plan.tagline}</p>
                <ul className="mt-6 flex-1 space-y-3">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-start gap-2.5 text-sm text-slate-300">
                      <Check size={17} className="mt-0.5 shrink-0 text-brand-400" />
                      {f}
                    </li>
                  ))}
                </ul>
                <Button
                  to="/signup"
                  variant={plan.highlighted ? "primary" : "secondary"}
                  className="mt-8 w-full"
                >
                  {plan.price === 0 ? "Start free" : `Get ${plan.name}`}
                </Button>
              </div>
            );
          })}
        </div>

        <div className="mt-24">
          <FaqSection faqs={PRICING_FAQS} emitSchema={false} />
        </div>
      </main>
      <Footer />
    </div>
  );
}
