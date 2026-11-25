import { cn } from "@/lib/utils";

/**
 * How an approval reads at a glance, in one place so it reads the same on the
 * queue, the detail page and the purchase order it belongs to.
 *
 * Note what the colours say. `info_requested` is amber rather than grey: a
 * request waiting on an answer is stalled, not progressing, and showing it as
 * quietly in-flight is how something sits for three weeks because the approver
 * is waiting on the submitter and the submitter does not know.
 */
export const REQUEST_STATUS = {
  pending: { label: "Awaiting approval", tone: "amber" },
  info_requested: { label: "Question asked", tone: "amber" },
  approved: { label: "Approved", tone: "emerald" },
  rejected: { label: "Rejected", tone: "rose" },
  cancelled: { label: "Cancelled", tone: "slate" },
};

export const STEP_STATUS = {
  pending: { label: "Waiting", tone: "slate" },
  approved: { label: "Approved", tone: "emerald" },
  rejected: { label: "Rejected", tone: "rose" },
  skipped: { label: "Not needed", tone: "slate" },
};

const TONES = {
  slate: "border-white/10 bg-white/[0.05] text-slate-300",
  amber: "border-amber-500/30 bg-amber-500/10 text-amber-200",
  emerald: "border-emerald-500/30 bg-emerald-500/10 text-emerald-200",
  rose: "border-rose-500/30 bg-rose-500/10 text-rose-200",
};

/** Plain words for an audit-trail action. */
export const EVENT_LABEL = {
  submitted: "Submitted",
  approved: "Approved",
  rejected: "Rejected",
  info_requested: "Asked a question",
  info_provided: "Answered",
  delegated: "Delegated",
  reminded: "Sent a reminder",
  cancelled: "Cancelled",
  level_completed: "Level completed",
};

export function ApprovalBadge({ status, className }) {
  const entry = REQUEST_STATUS[status] ?? { label: status, tone: "slate" };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium whitespace-nowrap",
        TONES[entry.tone],
        className,
      )}
    >
      {entry.label}
    </span>
  );
}

export function StepBadge({ status, className }) {
  const entry = STEP_STATUS[status] ?? { label: status, tone: "slate" };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        TONES[entry.tone],
        className,
      )}
    >
      {entry.label}
    </span>
  );
}

/**
 * The chain, level by level.
 *
 * Levels are shown as separate groups because that is what they are: level 2
 * is not asked until level 1 is done, and flattening the list into one column
 * of names would suggest everyone is being asked at once.
 */
export function ApprovalChain({ steps, currentLevel, className }) {
  const levels = [...new Set((steps ?? []).map((step) => step.level))].sort(
    (a, b) => a - b,
  );
  if (!levels.length) return null;

  return (
    <ol className={cn("space-y-3", className)}>
      {levels.map((level) => {
        const atLevel = steps.filter((step) => step.level === level);
        const active = level === currentLevel;
        const requireAll = atLevel.some((step) => step.requireAll);
        return (
          <li
            key={level}
            className={cn(
              "rounded-xl border p-3",
              active
                ? "border-amber-400/30 bg-amber-500/[0.06]"
                : "border-white/[0.07] bg-white/[0.02]",
            )}
          >
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
              <span className="font-medium text-slate-300">Level {level}</span>
              {active && <span className="text-amber-300">· waiting here</span>}
              <span className="text-slate-500">
                ·{" "}
                {atLevel.length === 1
                  ? "one approver"
                  : requireAll
                    ? `all ${atLevel.length} must approve`
                    : `any one of ${atLevel.length}`}
              </span>
            </div>
            <ul className="mt-2 space-y-1.5">
              {atLevel.map((step) => (
                <li
                  key={step.id}
                  className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-sm"
                >
                  <span className="text-slate-200">
                    {step.approver ?? "Unassigned"}
                  </span>
                  {step.approverRole && (
                    <span className="text-xs text-slate-500">
                      {step.approverRole.replace(/_/g, " ")}
                    </span>
                  )}
                  <StepBadge status={step.status} />
                  {step.onBehalf && (
                    <span className="text-xs text-slate-500">
                      by {step.actedBy}
                    </span>
                  )}
                  {step.comment && (
                    <span className="w-full text-xs italic text-slate-400">
                      “{step.comment}”
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </li>
        );
      })}
    </ol>
  );
}
