import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  FileText, CheckCircle2, AlertCircle, Clock, Copy, Gauge, Timer, Loader2,
} from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Processing statistics for the dashboard.
 *
 * Every number comes from one request, and the plan allowance in it is the
 * same value billing enforces - computed by the same code, not recalculated
 * here. A dashboard that disagreed with the invoice would make both numbers
 * worthless.
 */

function formatDuration(ms) {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatRate(rate) {
  // null means nothing has finished yet. Showing 0% would read as "everything
  // fails" rather than "nothing has run".
  if (rate == null) return "—";
  return `${Math.round(rate * 100)}%`;
}

function Tile({ icon: Icon, label, value, hint, tone = "default", to }) {
  const tones = {
    default: "text-slate-300",
    good: "text-emerald-300",
    warn: "text-amber-300",
    bad: "text-rose-300",
  };
  const body = (
    <>
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-slate-500">
        <Icon size={14} /> {label}
      </div>
      <div className={cn("mt-2 text-2xl font-semibold tabular-nums", tones[tone])}>
        {value}
      </div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </>
  );

  const className = cn(
    "glass rounded-2xl p-4",
    to && "transition-colors hover:bg-white/[0.04]",
  );
  // Only the tiles that lead somewhere useful are links; a tile that looks
  // clickable and is not is worse than a plain one.
  return to ? (
    <Link to={to} className={className}>{body}</Link>
  ) : (
    <div className={className}>{body}</div>
  );
}

export function UsageStats() {
  const [stats, setStats] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    api
      .get("/api/usage/stats")
      .then(({ data }) => active && setStats(data))
      .catch(() => active && setFailed(true));
    return () => {
      active = false;
    };
  }, []);

  if (failed) return null; // the dashboard still works without this panel
  if (!stats) {
    return (
      <div className="grid place-items-center py-10">
        <Loader2 className="animate-spin text-brand-400" size={20} />
      </div>
    );
  }

  const p = stats.processing;
  const usage = stats.usage;
  const limitLabel =
    usage.limit == null ? "Unlimited" : `${usage.used} / ${usage.limit}`;

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Tile
          icon={FileText}
          label="Processed"
          value={p.completed.toLocaleString()}
          hint={p.total !== p.completed ? `${p.total} uploaded in total` : "All succeeded"}
          tone="default"
        />
        <Tile
          icon={Gauge}
          label="Success rate"
          value={formatRate(p.successRate)}
          hint={p.failed > 0 ? `${p.failed} failed` : "No failures"}
          tone={p.successRate != null && p.successRate < 0.9 ? "warn" : "good"}
        />
        <Tile
          icon={Timer}
          label="Avg. time"
          value={formatDuration(p.averageProcessingMs)}
          hint="Per completed document"
        />
        <Tile
          icon={CheckCircle2}
          label="This month"
          value={limitLabel}
          hint={
            usage.remaining == null
              ? `${usage.planName} plan`
              : `${usage.remaining} left on ${usage.planName}`
          }
          tone={usage.atLimit ? "bad" : "default"}
          to="/dashboard/billing"
        />
      </div>

      {/* Only shown when there is something to act on. Tiles reading zero teach
          people to stop looking at this row. */}
      {(p.awaitingReview > 0 || p.unresolvedDuplicates > 0 || p.processing > 0) && (
        <div className="grid gap-3 sm:grid-cols-3">
          {p.awaitingReview > 0 && (
            <Tile
              icon={AlertCircle}
              label="Needs review"
              value={p.awaitingReview.toLocaleString()}
              hint="Validation flagged something"
              tone="warn"
              to="/dashboard/history?validationStatus=requires_review"
            />
          )}
          {p.unresolvedDuplicates > 0 && (
            <Tile
              icon={Copy}
              label="Possible duplicates"
              value={p.unresolvedDuplicates.toLocaleString()}
              hint="Awaiting a decision"
              tone="bad"
              to="/dashboard/history"
            />
          )}
          {p.processing > 0 && (
            <Tile
              icon={Clock}
              label="In progress"
              value={p.processing.toLocaleString()}
              hint="Still extracting"
            />
          )}
        </div>
      )}
    </div>
  );
}
