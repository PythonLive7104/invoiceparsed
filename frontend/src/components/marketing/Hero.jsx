import { motion } from "framer-motion";
import { Sparkles, ArrowRight, Zap } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { HERO } from "@/content/home";

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
            {HERO.eyebrow}
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.05, ease: [0.22, 1, 0.36, 1] }}
            className="mt-6 text-balance text-5xl font-semibold leading-[1.05] tracking-tight text-white sm:text-6xl lg:text-7xl"
          >
            {HERO.title.lead}
            <span className="gradient-text">{HERO.title.highlight}</span>
            {HERO.title.tail}
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.12, ease: [0.22, 1, 0.36, 1] }}
            className="mt-6 max-w-xl text-lg leading-relaxed text-slate-400"
          >
            {HERO.subhead}
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.18, ease: [0.22, 1, 0.36, 1] }}
            className="mt-9 flex flex-col gap-3 sm:flex-row sm:items-center"
          >
            <Button to={HERO.primaryCta.to} size="lg">
              {HERO.primaryCta.label}
              <ArrowRight size={18} />
            </Button>
            <Button href={HERO.secondaryCta.href} variant="outline" size="lg">
              {HERO.secondaryCta.label}
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
          <div className="glass overflow-hidden rounded-2xl border border-white/10 shadow-glow-sm">
            <div className="flex items-center gap-1.5 border-b border-white/[0.06] px-4 py-2.5">
              <span className="h-2.5 w-2.5 rounded-full bg-red-400/70" />
              <span className="h-2.5 w-2.5 rounded-full bg-amber-400/70" />
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-400/70" />
              <span className="ml-2 inline-flex items-center gap-1 text-[11px] text-slate-500">
                <Sparkles size={11} className="text-accent-cyan" /> InvoiceParsed — live demo
              </span>
            </div>
            {/* Muted + autoplay + loop is the only combination browsers allow to
                play inline without a click; playsInline stops iOS going fullscreen.
                The asset lives in /public (demo.mp4); poster shows while it loads. */}
            <video
              className="block w-full bg-ink-950"
              autoPlay
              muted
              loop
              playsInline
              preload="metadata"
              poster="/demo-poster.jpg"
              aria-label="InvoiceParsed demo: uploading an invoice and exporting structured data"
            >
              <source src="/demo.mp4" type="video/mp4" />
            </video>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
