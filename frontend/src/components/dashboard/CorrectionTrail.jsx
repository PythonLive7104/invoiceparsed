import { useState } from "react";
import { History, ChevronDown, ChevronRight, ArrowRight } from "lucide-react";

/**
 * What people have changed on this document.
 *
 * Collapsed by default: on a correct extraction there is nothing to see, and an
 * always-open empty panel is noise. The original value is never removed from
 * the record, so this stays an accurate account of what the document said
 * before anyone touched it.
 */

const FIELD_LABELS = {
  invoice_number: "Invoice number",
  invoice_date: "Invoice date",
  due_date: "Due date",
  purchase_order_reference: "PO reference",
  payment_terms: "Payment terms",
  tax_percentage: "Tax %",
  other_charges: "Other charges",
  amount_paid: "Amount paid",
  balance_due: "Balance due",
};

/** "line_items.2.unit_price" -> "Line 3 · Unit price" */
function labelFor(path) {
  const parts = path.split(".");
  if (parts[0] === "line_items" && parts.length >= 3) {
    const line = Number(parts[1]) + 1;
    return `Line ${line} · ${pretty(parts[2])}`;
  }
  if (parts.length === 2) return `${pretty(parts[0])} · ${pretty(parts[1])}`;
  return FIELD_LABELS[path] ?? pretty(path);
}

function pretty(key) {
  return (
    FIELD_LABELS[key] ??
    key.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase())
  );
}

function Value({ children }) {
  const empty = children === null || children === undefined || children === "";
  return (
    <span
      className={
        empty
          ? "italic text-slate-600"
          : "rounded bg-white/[0.06] px-1.5 py-0.5 font-mono text-[11px] text-slate-200"
      }
    >
      {empty ? "empty" : children}
    </span>
  );
}

export function CorrectionTrail({ corrections }) {
  const [open, setOpen] = useState(false);
  if (!corrections?.length) return null;

  return (
    <div className="mt-6 border-t border-white/[0.06] pt-4">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 text-left text-xs font-medium uppercase tracking-wide text-slate-500 transition-colors hover:text-slate-300"
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <History size={14} />
        {corrections.length} manual correction{corrections.length === 1 ? "" : "s"}
      </button>

      {open && (
        <ul className="mt-3 space-y-2.5">
          {corrections.map((c) => (
            <li key={c.id} className="text-xs leading-relaxed">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="font-medium text-slate-300">{labelFor(c.field)}</span>
                <Value>{c.from}</Value>
                <ArrowRight size={11} className="text-slate-600" />
                <Value>{c.to}</Value>
              </div>
              <div className="mt-0.5 text-slate-500">
                {c.by || "Unknown"}
                {c.at && ` · ${new Date(c.at).toLocaleString()}`}
                {c.reason && ` · ${c.reason}`}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
