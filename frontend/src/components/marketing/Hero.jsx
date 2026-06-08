import { motion } from "framer-motion";
import { Sparkles, FileText, ArrowRight, Zap } from "lucide-react";
import { Button } from "@/components/ui/Button";

const jsonLines = [
  { t: "{", key: false },
  { t: '"vendor": { "name": "Acme Corp", … },', key: true },
  { t: '"invoice_number": "INV-2024-0042",', key: true },
  { t: '"invoice_date": "2024-03-15",', key: true },
  { t: '"due_date": "2024-04-14",', key: true },
  { t: '"currency": "USD",', key: true },
  { t: '"line_items": [ … ],', key: true },
  { t: '"subtotal": 1500.00,', key: true },
  { t: '"tax": 120.00,', key: true },
  { t: '"total": 1620.00', key: true },
  { t: "}", key: false },
];

export function Hero() {
  return (
    <section className="relative overflow-hidden pt-32 pb-20 sm:pt-40 sm:pb-28">
      <div className="pointer-events-none absolute -top-40 left-1/2 h-[520px] w-[820px] -translate-x-1/2 rounded-full bg-radial-glow blur-2xl" />
      <div className="pointer-events-none absolute inset-0 bg-dots opacity-40 [mask-image:radial-gradient(ellipse_at_top,black,transparent_70%)]" />

      <div className="container-page relative grid items-center gap-14 lg:grid-cols-[1.05fr_1fr]">
        <div>
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
            className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3.5 py-1.5 text-xs font-medium text-slate-300"
          >
            <Sparkles size={14} className="text-accent-cyan" />
            Powered by OpenAI vision models
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.05, ease: [0.22, 1, 0.36, 1] }}
            className="mt-6 text-balance text-5xl font-semibold leading-[1.05] tracking-tight text-white sm:text-6xl lg:text-7xl"
          >
            Turn any invoice into <span className="gradient-text">clean data</span> in seconds.
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.12, ease: [0.22, 1, 0.36, 1] }}
            className="mt-6 max-w-xl text-lg leading-relaxed text-slate-400"
          >
            Stop typing invoices into spreadsheets. Upload a PDF or photo and get vendor, line
            items, taxes and totals as structured JSON or CSV — instantly, accurately,
            automatically.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.18, ease: [0.22, 1, 0.36, 1] }}
            className="mt-9 flex flex-col gap-3 sm:flex-row sm:items-center"
          >
            <Button to="/signup" size="lg">
              Extract your first invoice
              <ArrowRight size={18} />
            </Button>
            <Button href="#how" variant="outline" size="lg">
              See how it works
            </Button>
          </motion.div>

          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.8, delay: 0.3 }}
            className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-slate-500"
          >
            <span className="flex items-center gap-2">
              <Zap size={15} className="text-accent-violet" /> &lt; 5 sec average
            </span>
            <span className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" /> 95%+ accuracy
            </span>
            <span>No credit card · 5 free invoices</span>
          </motion.div>
        </div>

        <motion.div
          initial={{ opacity: 0, scale: 0.96, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
          className="relative"
        >
          <div className="relative mx-auto flex max-w-md flex-col items-stretch gap-3 sm:grid sm:max-w-none sm:grid-cols-[1fr_auto_1fr] sm:items-center">
            <div className="glass animate-float rounded-2xl p-4 [animation-delay:-1s]">
              <div className="flex items-center gap-2 text-slate-400">
                <FileText size={16} />
                <span className="text-xs">invoice.pdf</span>
              </div>
              <div className="mt-3 space-y-2">
                <div className="h-2.5 w-2/3 rounded bg-white/10" />
                <div className="h-2 w-1/2 rounded bg-white/[0.06]" />
                <div className="mt-3 space-y-1.5">
                  {[1, 2, 3, 4].map((i) => (
                    <div key={i} className="flex justify-between gap-2">
                      <div className="h-2 w-2/3 rounded bg-white/[0.06]" />
                      <div className="h-2 w-10 rounded bg-white/[0.06]" />
                    </div>
                  ))}
                </div>
                <div className="mt-3 flex justify-between border-t border-white/10 pt-2">
                  <div className="h-2.5 w-12 rounded bg-white/10" />
                  <div className="h-2.5 w-14 rounded bg-brand-400/50" />
                </div>
              </div>
            </div>

            <div className="relative grid place-items-center">
              <span className="absolute h-10 w-10 rounded-full bg-brand-500/40 animate-pulse-ring" />
              <span className="relative grid h-10 w-10 place-items-center rounded-full bg-brand-gradient text-white shadow-glow-sm">
                <Sparkles size={18} />
              </span>
            </div>

            <div className="glass overflow-hidden rounded-2xl">
              <div className="flex items-center gap-1.5 border-b border-white/[0.06] px-4 py-2.5">
                <span className="h-2.5 w-2.5 rounded-full bg-red-400/70" />
                <span className="h-2.5 w-2.5 rounded-full bg-amber-400/70" />
                <span className="h-2.5 w-2.5 rounded-full bg-emerald-400/70" />
                <span className="ml-2 text-[11px] text-slate-500">output.json</span>
              </div>
              <pre className="overflow-x-auto whitespace-pre-wrap break-words p-4 font-mono text-[11px] leading-relaxed sm:text-xs">
                {jsonLines.map((line, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, x: 8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.6 + i * 0.07, duration: 0.4 }}
                    style={{ paddingLeft: line.key ? 12 : 0 }}
                    className={line.key ? "text-accent-cyan" : "text-slate-400"}
                  >
                    {line.t}
                  </motion.div>
                ))}
              </pre>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
