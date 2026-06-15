import { Link } from "react-router-dom";
import { MarketingNav } from "@/components/marketing/MarketingNav";
import { Footer } from "@/components/marketing/Footer";
import { SEO } from "@/components/seo/SEO";
import { BLOG_POSTS } from "@/content/registry";
import { PAGE_META } from "@/content/pages";
import { formatDate } from "@/lib/utils";

export default function BlogIndex() {
  const meta = PAGE_META["/blog"];
  return (
    <div className="min-h-screen bg-ink-950">
      <SEO title={meta.title} description={meta.description} path="/blog" />
      <MarketingNav />
      <main className="mx-auto w-full max-w-3xl px-5 pb-20 pt-28">
        <h1 className="text-3xl font-semibold tracking-tight text-white sm:text-4xl">
          Invoice automation guides
        </h1>
        <p className="mt-5 text-lg leading-relaxed text-slate-200">
          Practical, answer-first guides on extracting data from invoices, choosing
          an OCR tool, and automating invoice data entry.
        </p>
        <ul className="mt-12 space-y-8 border-t border-white/10 pt-8">
          {BLOG_POSTS.map((post) => (
            <li key={post.slug}>
              <Link to={`/blog/${post.slug}`} className="group block">
                <h2 className="text-xl font-semibold text-white group-hover:text-brand-300">
                  {post.title}
                </h2>
                <p className="mt-2 text-sm leading-relaxed text-slate-400">{post.description}</p>
                <p className="mt-2 text-xs text-slate-500">
                  <time dateTime={post.datePublished}>{formatDate(post.datePublished)}</time>
                </p>
              </Link>
            </li>
          ))}
        </ul>
      </main>
      <Footer />
    </div>
  );
}
