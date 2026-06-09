import { Link } from "react-router-dom";
import { Infinity as InfinityIcon, Zap } from "lucide-react";
import { cn } from "@/lib/utils";

export function UsageMeter({ usage, compact = false }) {
  if (!usage) return null;
  const unlimited = usage.limit === null;
  const pct = unlimited
    ? 0
    : Math.min(100, Math.round((usage.used / Math.max(1, usage.limit)) * 100));

  const danger = !unlimited && pct >= 100;
  const warn = !unlimited && pct >= 80 && !danger;

  return (
    <div
      className={cn(
        "rounded-xl border border-white/[0.07] bg-white/[0.02]",
        compact ? "p-3.5" : "p-5",
      )}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-slate-500">
          This month
        </span>
        <span className="rounded-md bg-white/[0.06] px-1.5 py-0.5 text-[11px] font-medium capitalize text-slate-300">
          {usage.planName}
        </span>
      </div>

      {unlimited ? (
        <div className="mt-2.5 flex items-center gap-2 text-white">
          <InfinityIcon size={18} className="text-brand-300" />
          <span className="text-sm font-medium">{usage.used} documents · Unlimited</span>
        </div>
      ) : (
        <>
          <div className="mt-2.5 flex items-baseline gap-1.5">
            <span className="text-xl font-semibold text-white">{usage.used}</span>
            <span className="text-sm text-slate-500">/ {usage.limit}</span>
          </div>
          <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-white/[0.07]">
            <div
              className={cn(
                "h-full rounded-full transition-all duration-500",
                danger ? "bg-red-400" : warn ? "bg-amber-400" : "bg-brand-gradient",
              )}
              style={{ width: `${Math.max(4, pct)}%` }}
            />
          </div>
          {(warn || danger) && (
            <Link
              to="/dashboard/billing"
              className="mt-3 flex items-center justify-center gap-1.5 rounded-lg bg-brand-500/15 px-3 py-1.5 text-xs font-medium text-brand-200 ring-1 ring-inset ring-brand-400/20 transition-colors hover:bg-brand-500/25"
            >
              <Zap size={13} />
              {danger ? "Limit reached — upgrade" : "Running low — upgrade"}
            </Link>
          )}
        </>
      )}
    </div>
  );
}
