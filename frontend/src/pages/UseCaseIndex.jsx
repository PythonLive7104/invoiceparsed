import { Link } from "react-router-dom";
import { MarketingNav } from "@/components/marketing/MarketingNav";
import { Footer } from "@/components/marketing/Footer";
import { SEO } from "@/components/seo/SEO";
import { USE_CASES } from "@/content/registry";
import { PAGE_META } from "@/content/pages";

export default function UseCaseIndex() {
  const meta = PAGE_META["/use-cases"];
  return (
    <div className="min-h-screen bg-ink-950">
      <SEO title={meta.title} titleRaw={meta.titleRaw} description={meta.description} path="/use-cases" />
      <MarketingNav />
      <main className="mx-auto w-full max-w-3xl px-5 pb-20 pt-28">
        <h1 className="text-3xl font-semibold tracking-tight text-white sm:text-4xl">Use cases</h1>
        <p className="mt-5 text-lg leading-relaxed text-slate-200">
          How freelancers, small businesses and finance teams use InvoiceParsed to automate invoice
          and receipt data entry.
        </p>
        <ul className="mt-12 space-y-8 border-t border-white/10 pt-8">
          {USE_CASES.map((u) => (
            <li key={u.slug}>
              <Link to={`/use-cases/${u.slug}`} className="group block">
                <h2 className="text-xl font-semibold text-white group-hover:text-brand-300">{u.title}</h2>
                <p className="mt-2 text-sm leading-relaxed text-slate-400">{u.description}</p>
              </Link>
            </li>
          ))}
        </ul>
      </main>
      <Footer />
    </div>
  );
}
