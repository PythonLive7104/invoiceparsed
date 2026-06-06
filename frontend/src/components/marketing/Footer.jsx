import { Logo } from "@/components/ui/Logo";

const groups = [
  {
    title: "Product",
    links: ["Features", "Pricing", "API", "Dashboard"],
  },
  { title: "Company", links: ["About", "Blog", "Careers", "Contact"] },
  { title: "Legal", links: ["Privacy", "Terms", "Security", "DPA"] },
];

export function Footer() {
  return (
    <footer className="relative border-t border-white/[0.06] py-14">
      <div className="container-page grid gap-10 md:grid-cols-[1.4fr_1fr_1fr_1fr]">
        <div>
          <Logo />
          <p className="mt-4 max-w-xs text-sm leading-relaxed text-slate-500">
            AI-powered invoice data extraction for small businesses and freelancers. Upload,
            extract, export — in seconds.
          </p>
        </div>
        {groups.map((g) => (
          <div key={g.title}>
            <h4 className="text-sm font-semibold text-white">{g.title}</h4>
            <ul className="mt-4 space-y-2.5">
              {g.links.map((l) => (
                <li key={l}>
                  <a
                    href="#"
                    className="text-sm text-slate-500 transition-colors hover:text-slate-200"
                  >
                    {l}
                  </a>
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
