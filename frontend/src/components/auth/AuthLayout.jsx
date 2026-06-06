import { Link } from "react-router-dom";
import { Sparkles, Quote } from "lucide-react";
import { Logo } from "@/components/ui/Logo";

export function AuthLayout({ children }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="relative flex flex-col px-6 py-8 sm:px-10">
        <div className="flex items-center justify-between">
          <Logo />
          <Link to="/" className="text-sm text-slate-400 transition-colors hover:text-white">
            ← Back home
          </Link>
        </div>
        <div className="flex flex-1 items-center justify-center py-12">{children}</div>
      </div>

      <div className="relative hidden overflow-hidden border-l border-white/[0.06] bg-ink-900/40 lg:block">
        <div className="pointer-events-none absolute inset-0 bg-dots opacity-40" />
        <div className="pointer-events-none absolute -right-20 top-1/4 h-96 w-96 rounded-full bg-radial-glow blur-2xl" />
        <div className="relative flex h-full flex-col justify-center px-14">
          <span className="inline-flex w-fit items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs font-medium text-accent-cyan">
            <Sparkles size={14} /> Powered by OpenAI
          </span>
          <h2 className="mt-6 max-w-md text-balance text-4xl font-semibold leading-tight tracking-tight text-white">
            Reclaim hours every week with{" "}
            <span className="gradient-text">automated extraction</span>.
          </h2>
          <p className="mt-4 max-w-sm text-slate-400">
            Upload any invoice and get clean, structured data — vendor, line items, taxes and
            totals — in seconds.
          </p>

          <div className="glass mt-12 max-w-md rounded-2xl p-6">
            <Quote size={22} className="text-brand-400" />
            <p className="mt-3 text-sm leading-relaxed text-slate-300">
              “I used to spend 2+ hours a week logging client invoices into a spreadsheet. Now
              it's a 10-second drag and drop.”
            </p>
            <div className="mt-4 flex items-center gap-3">
              <div className="grid h-9 w-9 place-items-center rounded-full bg-brand-gradient text-sm font-semibold text-white">
                S
              </div>
              <div className="text-sm">
                <div className="font-medium text-white">Sarah</div>
                <div className="text-slate-500">Freelance Designer</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
