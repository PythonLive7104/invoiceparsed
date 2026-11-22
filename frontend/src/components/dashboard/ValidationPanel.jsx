import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";
import { cn } from "@/lib/utils.js";

/**
 * Validation verdict for an extracted invoice.
 *
 * The backend recomputes this on every read, so it stays correct after an edit
 * rather than showing a stale verdict. Each issue names the actual figures
 * ("Line items add up to 220.00 but the subtotal says 260.00"), because a
 * finance person needs to know what to look at, not that "something is wrong".
 */

const STATUS = {
  valid: {
    label: "Valid",
    hint: "Everything checks out.",
    Icon: CheckCircle2,
    tone: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
    dot: "text-emerald-400",
  },
  valid_with_warnings: {
    label: "Valid, with warnings",
    hint: "Usable, but worth a glance.",
    Icon: Info,
    tone: "border-sky-500/30 bg-sky-500/10 text-sky-300",
    dot: "text-sky-400",
  },
  requires_review: {
    label: "Needs review",
    hint: "Something does not add up. Check before approving.",
    Icon: AlertTriangle,
    tone: "border-amber-500/30 bg-amber-500/10 text-amber-300",
    dot: "text-amber-400",
  },
  invalid: {
    label: "Invalid",
    hint: "Required information is missing.",
    Icon: XCircle,
    tone: "border-rose-500/30 bg-rose-500/10 text-rose-300",
    dot: "text-rose-400",
  },
};

const SEVERITY_ICON = {
  error: { Icon: XCircle, className: "text-rose-400" },
  review: { Icon: AlertTriangle, className: "text-amber-400" },
  warning: { Icon: Info, className: "text-sky-400" },
};

/** Compact badge for list rows and card headers. */
export function ValidationBadge({ validation, className }) {
  if (!validation?.status) return null;
  const meta = STATUS[validation.status] ?? STATUS.valid_with_warnings;
  const { Icon } = meta;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
        meta.tone,
        className,
      )}
      title={meta.hint}
    >
      <Icon size={13} />
      {meta.label}
      {validation.issueCount > 0 && (
        <span className="opacity-70">· {validation.issueCount}</span>
      )}
    </span>
  );
}

/** Full verdict with the list of findings. */
export function ValidationPanel({ validation }) {
  if (!validation?.status) return null;
  const meta = STATUS[validation.status] ?? STATUS.valid_with_warnings;
  const { Icon } = meta;
  const issues = validation.issues ?? [];

  return (
    <div className={cn("rounded-xl border p-4", meta.tone)}>
      <div className="flex items-start gap-3">
        <Icon size={18} className={cn("mt-0.5 shrink-0", meta.dot)} />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold">{meta.label}</div>
          <p className="mt-0.5 text-xs opacity-80">{meta.hint}</p>

          {issues.length > 0 && (
            <ul className="mt-3 space-y-2">
              {issues.map((issue, index) => {
                const severity = SEVERITY_ICON[issue.severity] ?? SEVERITY_ICON.warning;
                const SeverityIcon = severity.Icon;
                return (
                  <li
                    key={`${issue.code}-${index}`}
                    className="flex items-start gap-2 text-xs leading-relaxed text-slate-200"
                  >
                    <SeverityIcon
                      size={13}
                      className={cn("mt-0.5 shrink-0", severity.className)}
                    />
                    <span>{issue.message}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
