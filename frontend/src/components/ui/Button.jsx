import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";

const base =
  "relative inline-flex items-center justify-center gap-2 rounded-xl font-medium transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400/70 focus-visible:ring-offset-2 focus-visible:ring-offset-ink-950 disabled:opacity-50 disabled:pointer-events-none select-none";

const variants = {
  primary:
    "text-white bg-brand-gradient shadow-glow-sm hover:shadow-glow hover:brightness-110 active:scale-[0.98]",
  secondary:
    "text-white bg-white/[0.06] border border-white/10 hover:bg-white/[0.1] active:scale-[0.98]",
  outline:
    "text-slate-200 border border-white/15 hover:border-brand-400/60 hover:text-white hover:bg-white/[0.04]",
  ghost: "text-slate-300 hover:text-white hover:bg-white/[0.06]",
};

const sizes = {
  sm: "h-9 px-3.5 text-sm",
  md: "h-11 px-5 text-sm",
  lg: "h-[52px] px-7 text-base",
};

export function Button({
  variant = "primary",
  size = "md",
  className,
  children,
  to,
  href,
  ...rest
}) {
  const classes = cn(base, variants[variant], sizes[size], className);

  if (to) {
    return (
      <Link to={to} className={classes} {...rest}>
        {children}
      </Link>
    );
  }
  if (href) {
    return (
      <a href={href} className={classes} {...rest}>
        {children}
      </a>
    );
  }
  return (
    <button className={classes} {...rest}>
      {children}
    </button>
  );
}
