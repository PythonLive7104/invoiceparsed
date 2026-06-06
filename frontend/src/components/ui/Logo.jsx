import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";

export function LogoMark({ className }) {
  return (
    <span
      className={cn(
        "relative grid place-items-center rounded-xl bg-brand-gradient shadow-glow-sm",
        className,
      )}
    >
      <svg viewBox="0 0 24 24" fill="none" className="h-[60%] w-[60%] text-white" aria-hidden>
        <path
          d="M6 3.5h7.5L18 8v12.5H6z"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinejoin="round"
        />
        <path
          d="M12.5 11.2l.85 1.95 1.95.85-1.95.85-.85 1.95-.85-1.95L9.7 14l1.95-.85.85-1.95z"
          fill="currentColor"
        />
        <path d="M8.4 8.2h3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    </span>
  );
}

export function Logo({ className, to = "/" }) {
  return (
    <Link to={to} className={cn("group inline-flex items-center gap-2.5", className)}>
      <LogoMark className="h-9 w-9 transition-transform group-hover:scale-105" />
      <span className="text-lg font-semibold tracking-tight text-white">
        Invoice<span className="gradient-text">Parsed</span>
      </span>
    </Link>
  );
}
