import { cn } from "@/lib/utils";

/**
 * Purchase-order status, as a badge.
 *
 * The labels and colours live here rather than in each page so the lifecycle
 * reads the same everywhere. Note what the colours say: anything not yet
 * approved is amber or grey, never green — a glance at a list should not make
 * an unapproved commitment look like an authorized one.
 */
export const PO_STATUS = {
  draft: { label: "Draft", tone: "slate" },
  pending_approval: { label: "Awaiting approval", tone: "amber" },
  approved: { label: "Approved", tone: "emerald" },
  sent: { label: "Sent to supplier", tone: "sky" },
  partially_received: { label: "Partly received", tone: "sky" },
  fully_received: { label: "Received", tone: "emerald" },
  closed: { label: "Closed", tone: "slate" },
  cancelled: { label: "Cancelled", tone: "rose" },
};

const TONES = {
  slate: "border-white/10 bg-white/[0.05] text-slate-300",
  amber: "border-amber-500/30 bg-amber-500/10 text-amber-200",
  emerald: "border-emerald-500/30 bg-emerald-500/10 text-emerald-200",
  sky: "border-sky-500/30 bg-sky-500/10 text-sky-200",
  rose: "border-rose-500/30 bg-rose-500/10 text-rose-200",
};

/** Human label for a status, falling back to the raw value so an unknown
 *  status from a newer server still renders as words. */
export function poStatusLabel(status) {
  return PO_STATUS[status]?.label ?? String(status ?? "").replace(/_/g, " ");
}

export function PoStatusBadge({ status, className }) {
  const tone = PO_STATUS[status]?.tone ?? "slate";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium whitespace-nowrap",
        TONES[tone],
        className,
      )}
    >
      {poStatusLabel(status)}
    </span>
  );
}
