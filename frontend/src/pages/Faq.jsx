import { MarketingNav } from "@/components/marketing/MarketingNav";
import { Footer } from "@/components/marketing/Footer";
import { SEO } from "@/components/seo/SEO";
import { JsonLd } from "@/components/seo/JsonLd";
import { FaqSection } from "@/components/seo/FaqSection";
import { breadcrumbSchema } from "@/lib/schema";
import { SITE_FAQS } from "@/content/registry";
import { PAGE_META } from "@/content/pages";

export default function Faq() {
  const meta = PAGE_META["/faq"];
  return (
    <div className="min-h-screen bg-ink-950">
      <SEO title={meta.title} titleRaw={meta.titleRaw} description={meta.description} path="/faq" />
      <JsonLd data={breadcrumbSchema([{ name: "Home", path: "/" }, { name: "FAQ", path: "/faq" }])} />
      <MarketingNav />
      <main className="mx-auto w-full max-w-3xl px-5 pb-20 pt-28">
        {/* Answer-first opening paragraph (AEO) */}
        <h1 className="text-3xl font-semibold tracking-tight text-white sm:text-4xl">
          Frequently asked questions
        </h1>
        <p className="mt-5 text-lg leading-relaxed text-slate-200">
          InvoiceParsed is an AI invoice parser that extracts structured data from
          invoice PDFs and images in seconds. Below are answers to the questions we
          hear most about accuracy, formats, pricing and integrations.
        </p>
        <div className="mt-12">
          <FaqSection faqs={SITE_FAQS} title="" />
        </div>
      </main>
      <Footer />
    </div>
  );
}
