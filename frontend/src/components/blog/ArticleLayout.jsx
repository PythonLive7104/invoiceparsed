import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { MarketingNav } from "@/components/marketing/MarketingNav";
import { Footer } from "@/components/marketing/Footer";
import { SEO } from "@/components/seo/SEO";
import { FaqSection } from "@/components/seo/FaqSection";
import { ArticleBody } from "@/components/blog/ArticleBody";
import { formatDate } from "@/lib/utils";

/**
 * Reusable long-form layout for /blog/[slug], /compare/[slug] and
 * /use-cases/[slug]. Handles SEO head, Article + BreadcrumbList + FAQPage
 * JSON-LD, an answer-first intro, the body, and an FAQ section at the bottom.
 *
 * Props:
 *   post      { slug, title, description, excerpt, author?, datePublished?,
 *               dateModified?, image?, tags?, faqs? }
 *   kind      "blog" | "compare" | "use-cases"  (drives breadcrumb + base path)
 *   children  the article body (JSX)
 */
const KIND_META = {
  blog: { label: "Blog", base: "/blog" },
  compare: { label: "Compare", base: "/compare" },
  "use-cases": { label: "Use cases", base: "/use-cases" },
};

export function ArticleLayout({ post, kind = "blog", children }) {
  const meta = KIND_META[kind] || KIND_META.blog;
  const path = `${meta.base}/${post.slug}`;

  const crumbs = [
    { name: "Home", path: "/" },
    { name: meta.label, path: meta.base },
    { name: post.title, path },
  ];

  // Article/Breadcrumb/FAQPage JSON-LD is emitted by the prerenderer
  // (single source of truth — see scripts/prerender.mjs).

  return (
    <div className="min-h-screen bg-ink-950">
      <SEO
        title={post.title}
        description={post.description}
        path={path}
        image={post.image}
        type="article"
        article={{
          publishedTime: post.datePublished,
          modifiedTime: post.dateModified,
          author: post.author,
          tags: post.tags,
        }}
      />
      <MarketingNav />

      <article className="mx-auto w-full max-w-3xl px-5 pb-20 pt-28">
        {/* Visible breadcrumb (matches BreadcrumbList schema) */}
        <nav aria-label="Breadcrumb" className="mb-8 flex flex-wrap items-center gap-1.5 text-sm text-slate-500">
          {crumbs.map((c, i) => (
            <span key={c.path} className="flex items-center gap-1.5">
              {i > 0 && <ChevronRight size={13} className="text-slate-600" />}
              {i < crumbs.length - 1 ? (
                <Link to={c.path} className="hover:text-brand-300">{c.name}</Link>
              ) : (
                <span className="line-clamp-1 text-slate-400">{c.name}</span>
              )}
            </span>
          ))}
        </nav>

        <header>
          <h1 className="text-3xl font-semibold tracking-tight text-white sm:text-4xl">
            {post.title}
          </h1>
          {(post.author || post.datePublished) && (
            <p className="mt-3 text-sm text-slate-500">
              {post.author}
              {post.author && post.datePublished && " · "}
              {post.datePublished && (
                <time dateTime={post.datePublished}>{formatDate(post.datePublished)}</time>
              )}
            </p>
          )}
        </header>

        {/* Answer-first opening paragraph (AEO) */}
        {post.excerpt && (
          <p className="mt-6 border-l-2 border-brand-400/60 pl-4 text-lg leading-relaxed text-slate-200">
            {post.excerpt}
          </p>
        )}

        <div className="prose-invoice mt-8 space-y-5 text-base leading-relaxed text-slate-300">
          {post.content?.length ? <ArticleBody blocks={post.content} /> : children}
        </div>

        {post.faqs?.length > 0 && (
          <div className="mt-16">
            {/* Schema already emitted above, so disable it here to avoid duplicates. */}
            <FaqSection faqs={post.faqs} emitSchema={false} />
          </div>
        )}
      </article>

      <Footer />
    </div>
  );
}
