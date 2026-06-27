import { motion, useReducedMotion } from "framer-motion";
import { Sparkles, ArrowRight, Zap } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { HERO } from "@/content/home";

// Elegant staggered "cascade" arrival: each child fades and slides up in turn,
// using a snappy-yet-smooth bezier. Drives the eyebrow → headline → subhead →
// CTAs → trust-row sequence on the left column.
const container = {
  hidden: {},
  show: {
    transition: { staggerChildren: 0.15, delayChildren: 0.3 },
  },
};

const item = {
  hidden: { opacity: 0, y: 30 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.8, ease: [0.16, 1, 0.3, 1] },
  },
};

export function Hero() {
  // Always-on ambient motion keeps the hero feeling alive after the one-time
  // entrance cascade settles — but we honour prefers-reduced-motion (vestibular
  // safety) by freezing the looping animations for those users.
  const reduce = useReducedMotion();
  const glow = reduce ? undefined : { scale: [1, 1.08, 1], opacity: [0.65, 1, 0.65] };
  const float = reduce ? undefined : { y: [0, -12, 0] };

  return (
    <section className="relative overflow-hidden pt-32 pb-20 sm:pt-40 sm:pb-28">
      <motion.div
        aria-hidden
        animate={glow}
        transition={{ duration: 9, ease: "easeInOut", repeat: Infinity }}
        className="pointer-events-none absolute -top-40 left-1/2 h-[520px] w-[820px] -translate-x-1/2 rounded-full bg-radial-glow blur-2xl"
      />
      <div className="pointer-events-none absolute inset-0 bg-dots opacity-40 [mask-image:radial-gradient(ellipse_at_top,black,transparent_70%)]" />

      <div className="container-page relative grid items-center gap-14 lg:grid-cols-[1.05fr_1fr]">
        <motion.div variants={container} initial="hidden" animate="show">
          <motion.h1
            variants={item}
            className="text-balance text-5xl font-semibold leading-[1.05] tracking-tight text-white sm:text-6xl lg:text-7xl"
          >
            {HERO.title.lead}
            <span className="gradient-text">{HERO.title.highlight}</span>
            {HERO.title.tail}
          </motion.h1>

          <motion.p
            variants={item}
            className="mt-6 max-w-xl text-lg leading-relaxed text-slate-400"
          >
            {HERO.subhead}
          </motion.p>

          <motion.div
            variants={item}
            className="mt-9 flex flex-col gap-3 sm:flex-row sm:items-center"
          >
            <Button to={HERO.primaryCta.to} size="lg" className="group">
              {HERO.primaryCta.label}
              <ArrowRight
                size={18}
                className="transition-transform duration-200 group-hover:translate-x-1"
              />
            </Button>
            <Button href={HERO.secondaryCta.href} variant="outline" size="lg" className="group">
              {HERO.secondaryCta.label}
              <ArrowRight
                size={18}
                className="opacity-70 transition-all duration-200 group-hover:translate-x-1 group-hover:opacity-100"
              />
            </Button>
          </motion.div>

          <motion.div
            variants={item}
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
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.96, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={{ duration: 0.9, delay: 0.45, ease: [0.16, 1, 0.3, 1] }}
          className="relative"
        >
          <motion.div
            animate={float}
            transition={{ duration: 7, ease: "easeInOut", repeat: Infinity }}
            className="glass overflow-hidden rounded-2xl border border-white/10 shadow-glow-sm"
          >
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
          </motion.div>
        </motion.div>
      </div>
    </section>
  );
}
