import { useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  Building2,
  ClipboardList,
  GitCompareArrows,
  Lock,
  Sparkles,
  X,
} from "lucide-react";
import { useAuth } from "@/lib/auth.jsx";
import { PAYABLES } from "@/components/dashboard/UpgradePanel";
import { cn } from "@/lib/utils";

/**
 * A one-off announcement for people already using the product.
 *
 * Existing customers never revisit the landing page, so a feature they do not
 * stumble across is a feature they do not know exists. This is the only place
 * in the app that tells them.
 *
 * Dismissal is per-browser `localStorage` rather than a flag on the account,
 * deliberately: it is a convenience, not a decision worth a database column or
 * a migration, and the worst case of losing it is seeing one card again. Keyed
 * by release, so the next announcement is a new key rather than a new
 * component, and reads/writes are wrapped because a private window or blocked
 * site data makes `localStorage` throw rather than return empty.
 */
const RELEASE = "payables-2026-11";
const KEY = `invoiceparsed:whatsnew:${RELEASE}`;

function wasDismissed() {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

const ITEMS = [
  {
    to: "/dashboard/suppliers",
    icon: Building2,
    title: "Suppliers",
    desc: "One record per business you buy from. Invoices attach themselves on upload, and spend is totalled per supplier.",
  },
  {
    to: "/dashboard/purchase-orders",
    icon: ClipboardList,
    title: "Purchase orders",
    desc: "Record what you agreed to buy, route it for approval, and send the supplier a PDF.",
  },
  {
    to: "/dashboard/matching",
    icon: GitCompareArrows,
    title: "Invoice matching",
    desc: "Every arriving invoice checked against its order — prices, quantities, taxes and totals, with over-invoicing caught across invoices.",
  },
];

export function WhatsNew() {
  const { has } = useAuth();
  const [hidden, setHidden] = useState(wasDismissed);

  if (hidden) return null;
  const locked = !has(PAYABLES);

  function dismiss() {
    try {
      localStorage.setItem(KEY, "1");
    } catch {
      // A browser that refuses storage still gets the card closed for this
      // session; it will come back next time, which is a smaller problem than
      // a button that appears to do nothing.
    }
    setHidden(true);
  }

  return (
    <div className="relative overflow-hidden rounded-2xl border border-brand-400/25 bg-brand-500/[0.06] p-5 sm:p-6">
      <button
        type="button"
        onClick={dismiss}
        className="absolute right-3 top-3 grid h-7 w-7 place-items-center rounded-lg text-slate-500 transition-colors hover:bg-white/5 hover:text-slate-300"
        aria-label="Dismiss"
      >
        <X size={15} />
      </button>

      <div className="flex items-center gap-2 pr-8">
        <Sparkles size={16} className="shrink-0 text-brand-300" />
        <span className="text-xs font-semibold uppercase tracking-wider text-brand-300">
          New
        </span>
      </div>

      <h2 className="mt-2.5 text-lg font-semibold tracking-tight text-white">
        InvoiceParsed now runs your payables, not just your extraction
      </h2>
      <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-slate-400">
        Extraction told you what an invoice said. These three tell you whether
        you should pay it.
        {locked && " Included on the Pro plan and above."}
      </p>

      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        {ITEMS.map((item) => (
          <Link
            key={item.to}
            to={locked ? "/dashboard/billing" : item.to}
            className={cn(
              "group rounded-xl border border-white/[0.07] bg-ink-950/30 p-4",
              "transition-colors hover:border-brand-400/30 hover:bg-white/[0.04]",
            )}
          >
            <div className="flex items-center gap-2">
              <item.icon size={16} className="shrink-0 text-brand-300" />
              <span className="text-sm font-medium text-white">{item.title}</span>
              {locked && <Lock size={11} className="shrink-0 text-slate-600" />}
            </div>
            <p className="mt-1.5 text-xs leading-relaxed text-slate-500">
              {item.desc}
            </p>
          </Link>
        ))}
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-2">
        <Link
          to={locked ? "/dashboard/billing" : "/dashboard/purchase-orders"}
          className="group inline-flex items-center gap-1.5 text-sm font-medium text-brand-200 transition-colors hover:text-white"
        >
          {locked ? "See the Pro plan" : "Raise your first order"}
          <ArrowRight
            size={14}
            className="transition-transform group-hover:translate-x-0.5"
          />
        </Link>
        <button
          type="button"
          onClick={dismiss}
          className="text-sm text-slate-500 transition-colors hover:text-slate-300"
        >
          Not now
        </button>
      </div>
    </div>
  );
}
