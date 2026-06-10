import { Link } from "react-router-dom";
import { Logo } from "@/components/ui/Logo";
import { BLOG_POSTS, USE_CASES } from "@/content/registry";

// Internal links use <Link to>; external/placeholder use <a href>.
const groups = [
  {
    title: "Product",
    links: [
      { label: "Pricing", to: "/pricing" },
      { label: "FAQ", to: "/faq" },
      { label: "About", to: "/about" },
      { label: "Dashboard", to: "/dashboard" },
    ],
  },
  {
    title: "Guides",
    links: [
      { label: "Blog", to: "/blog" },
      ...BLOG_POSTS.map((p) => ({ label: p.title.replace(/ \(2026 Guide\)$/, ""), to: `/blog/${p.slug}` })),
    ],
  },
  {
    title: "Use cases",
    links: USE_CASES.map((u) => ({ label: u.title, to: `/use-cases/${u.slug}` })),
  },
  {
    title: "Company",
    links: [
      { label: "Contact", to: "/contact" },
      { label: "Privacy", href: "#" },
      { label: "Terms", href: "#" },
    ],
  },
];

function FooterLink({ link }) {
  const cls = "text-sm text-slate-500 transition-colors hover:text-slate-200";
  return link.to ? (
    <Link to={link.to} className={cls}>{link.label}</Link>
  ) : (
    <a href={link.href} className={cls}>{link.label}</a>
  );
}

export function Footer() {
  return (
    <footer className="relative border-t border-white/[0.06] py-14">
      <div className="container-page grid gap-10 md:grid-cols-[1.4fr_1fr_1fr_1fr_1fr]">
        <div>
          <Logo />
          <p className="mt-4 max-w-xs text-sm leading-relaxed text-slate-500">
            AI-powered invoice and receipt data extraction for small businesses and freelancers.
            Upload, extract, export — in seconds.
          </p>
        </div>
        {groups.map((g) => (
          <div key={g.title}>
            <h4 className="text-sm font-semibold text-white">{g.title}</h4>
            <ul className="mt-4 space-y-2.5">
              {g.links.map((l) => (
                <li key={l.label}>
                  <FooterLink link={l} />
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="container-page mt-12 flex flex-col items-center justify-between gap-3 border-t border-white/[0.06] pt-6 text-sm text-slate-500 sm:flex-row">
        <p>© {new Date().getFullYear()} InvoiceParsed. All rights reserved.</p>
        <p className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
          All systems operational
        </p>
      </div>
    </footer>
  );
}
