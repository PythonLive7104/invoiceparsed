import { Link } from "react-router-dom";
import { MarketingNav } from "@/components/marketing/MarketingNav";
import { Footer } from "@/components/marketing/Footer";
import { SEO } from "@/components/seo/SEO";
import { COMPARISONS } from "@/content/registry";
import { PAGE_META } from "@/content/pages";

export default function CompareIndex() {
  const meta = PAGE_META["/compare"];
  return (
    <div className="min-h-screen bg-ink-950">
      <SEO title={meta.title} titleRaw={meta.titleRaw} description={meta.description} path="/compare" />
      <MarketingNav />
      <main className="mx-auto w-full max-w-3xl px-5 pb-20 pt-28">
        <h1 className="text-3xl font-semibold tracking-tight text-white sm:text-4xl">Comparisons</h1>
        <p className="mt-5 text-lg leading-relaxed text-slate-200">
          See how InvoiceParsed stacks up against the alternatives for extracting invoice and
          receipt data.
        </p>
        <ul className="mt-12 space-y-8 border-t border-white/10 pt-8">
          {COMPARISONS.map((c) => (
            <li key={c.slug}>
              <Link to={`/compare/${c.slug}`} className="group block">
                <h2 className="text-xl font-semibold text-white group-hover:text-brand-300">{c.title}</h2>
                <p className="mt-2 text-sm leading-relaxed text-slate-400">{c.description}</p>
              </Link>
            </li>
          ))}
        </ul>
      </main>
      <Footer />
    </div>
  );
}
