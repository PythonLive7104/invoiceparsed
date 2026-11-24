import { Link } from "react-router-dom";
import { ArrowRight, Check, Lock } from "lucide-react";
import { Button } from "@/components/ui/Button";

/**
 * What a payables page shows an organization whose plan does not include it.
 *
 * Deliberately not a blank page or a redirect. Somebody who arrives here is
 * interested, and the useful thing to show them is what the module actually
 * does — the server has already refused the data, so this is a sales surface,
 * not a security boundary.
 */

/** The capability name, matching plans.py. */
export const PAYABLES = "payables";

export function UpgradePanel({
  title,
  blurb,
  points = [],
  plan = "Pro",
  icon: Icon = Lock,
}) {
  return (
    <div className="glass mx-auto max-w-2xl rounded-2xl p-7 sm:p-9">
      <span className="grid h-12 w-12 place-items-center rounded-2xl bg-brand-500/10 text-brand-300 ring-1 ring-inset ring-brand-400/20">
        <Icon size={22} />
      </span>

      <h1 className="mt-5 text-xl font-semibold tracking-tight text-white sm:text-2xl">
        {title}
      </h1>
      <p className="mt-2 text-sm leading-relaxed text-slate-400">{blurb}</p>

      {points.length > 0 && (
        <ul className="mt-6 space-y-2.5">
          {points.map((point) => (
            <li key={point} className="flex items-start gap-2.5 text-sm text-slate-300">
              <Check size={15} className="mt-0.5 shrink-0 text-brand-400" />
              <span>{point}</span>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-7 flex flex-wrap items-center gap-3">
        <Button to="/dashboard/billing" className="group">
          Upgrade to {plan}
          <ArrowRight
            size={16}
            className="transition-transform group-hover:translate-x-0.5"
          />
        </Button>
        <Link
          to="/pricing"
          className="text-sm text-slate-400 transition-colors hover:text-white"
        >
          Compare plans
        </Link>
      </div>

      <p className="mt-5 text-xs text-slate-500">
        Extraction, history and exports are unaffected by your plan's payables
        setting — this covers suppliers, purchase orders and invoice matching only.
      </p>
    </div>
  );
}

/** The copy for each payables page, so three pages describe one paywall once. */
export const PAYABLES_COPY = {
  suppliers: {
    title: "Supplier records are a Pro feature",
    blurb:
      "Keep one record per business you buy from, with every invoice attached to it automatically.",
    points: [
      "Invoices attach themselves to the right supplier on upload",
      "Spend per supplier, totalled per currency",
      "Duplicate-supplier detection on tax ID and name",
      "Bank details held behind their own permission, and never changed by a scan",
    ],
  },
  purchaseOrders: {
    title: "Purchase orders are a Pro feature",
    blurb:
      "Record what you have agreed to buy, get it approved, and send the supplier a PDF.",
    points: [
      "Line items, taxes and delivery dates, with totals the server computes",
      "Draft → approval → sent, with approval as a separate permission",
      "You cannot approve an order you raised yourself",
      "A downloadable PDF that marks anything unapproved as not an authorization",
    ],
  },
  matching: {
    title: "Invoice matching is a Pro feature",
    blurb:
      "Every arriving invoice checked against the order it bills — prices, quantities, taxes and totals.",
    points: [
      "Invoices linked to their purchase order automatically on upload",
      "Price, quantity and tax discrepancies reported with both figures named",
      "Over-invoicing caught across several invoices, not just one",
      "Tolerances you set, and an accepted discrepancy recorded against a name",
    ],
  },
};
