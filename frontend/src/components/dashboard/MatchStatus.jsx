import { cn } from "@/lib/utils";

/**
 * How a match reads at a glance, in one place so it reads the same everywhere.
 *
 * Note what the colours say. Only `matched` is green. A discrepancy is amber
 * and a failed comparison is red, and an accepted discrepancy stays amber
 * rather than turning green — somebody took responsibility for it, which is
 * not the same as the figures agreeing. Making it green would hide exactly the
 * invoices an auditor came to look at.
 */
export const OUTCOMES = {
  matched: { label: "Matched", tone: "emerald" },
  discrepancy: { label: "Discrepancy", tone: "amber" },
  failed: { label: "Does not match", tone: "rose" },
};

const TONES = {
  slate: "border-white/10 bg-white/[0.05] text-slate-300",
  amber: "border-amber-500/30 bg-amber-500/10 text-amber-200",
  emerald: "border-emerald-500/30 bg-emerald-500/10 text-emerald-200",
  sky: "border-sky-500/30 bg-sky-500/10 text-sky-200",
  rose: "border-rose-500/30 bg-rose-500/10 text-rose-200",
};

/** How each finding is coloured and ordered. `blocking` first, always. */
export const SEVERITY = {
  blocking: {
    label: "Must not be paid",
    tone: "rose",
    dot: "bg-rose-400",
    rank: 0,
  },
  review: { label: "Needs a look", tone: "amber", dot: "bg-amber-400", rank: 1 },
  info: { label: "For information", tone: "slate", dot: "bg-slate-500", rank: 2 },
};

export const MATCH_METHOD = {
  po_number: "PO number on the invoice",
  po_reference: "Order reference",
  supplier_amount: "Supplier and amount",
  manual: "Chosen by hand",
};

export function MatchOutcomeBadge({ outcome, overridden, className }) {
  const entry = OUTCOMES[outcome];
  if (!entry) {
    return (
      <span
        className={cn(
          "inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium",
          TONES.slate,
          className,
        )}
      >
        Not matched
      </span>
    );
  }
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium whitespace-nowrap",
        TONES[entry.tone],
        className,
      )}
    >
      {entry.label}
      {overridden && <span className="opacity-70">· accepted</span>}
    </span>
  );
}

/** Findings, worst first, each one coloured by what it means for a payment. */
export function FindingList({ findings, className }) {
  const items = [...(findings ?? [])].sort(
    (a, b) => (SEVERITY[a.severity]?.rank ?? 9) - (SEVERITY[b.severity]?.rank ?? 9),
  );
  if (!items.length) return null;

  return (
    <ul className={cn("space-y-1.5", className)}>
      {items.map((finding, index) => {
        const level = SEVERITY[finding.severity] ?? SEVERITY.info;
        return (
          <li
            key={`${finding.code}-${finding.lineNo ?? index}`}
            className="flex items-start gap-2.5 text-xs leading-relaxed"
          >
            <span
              className={cn("mt-1.5 size-1.5 shrink-0 rounded-full", level.dot)}
              aria-hidden
            />
            <span className="min-w-0">
              <span
                className={cn(
                  "text-slate-200",
                  finding.severity === "info" && "text-slate-400",
                )}
              >
                {finding.message}
              </span>
              {finding.lineNo != null && (
                <span className="ml-1.5 text-slate-500">(line {finding.lineNo})</span>
              )}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
