import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ChevronLeft,
  ChevronRight,
  GitCompareArrows,
  Loader2,
  Search,
  Settings2,
  ShieldAlert,
  X,
} from "lucide-react";
import { api, apiError } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/lib/auth.jsx";
import { PERMISSIONS } from "@/lib/permissions";
import { cn, formatDate, formatMoney } from "@/lib/utils";
import { poStatusLabel } from "@/components/dashboard/PoStatus";
import { MatchOutcomeBadge } from "@/components/dashboard/MatchStatus";

/**
 * Invoice-to-PO matching: the exceptions, and the tolerances behind them.
 *
 * The default view is deliberately not "everything". It is the invoices
 * somebody still has to deal with — unmatched, or matched with figures that
 * did not agree and nobody has accepted. A screen that opened on a long list
 * of successful matches would bury the three that matter.
 *
 * Tolerances live on this page rather than in Settings because that is where
 * the question gets asked: somebody looking at a one-cent discrepancy wants to
 * know what the bound is, and changing it there is one click instead of a hunt
 * through a settings tree.
 */

const FILTERS = [
  ["exceptions", "Needs attention"],
  ["blocked", "Must not be paid"],
  ["unmatched", "No order"],
  ["matched", "Matched"],
  ["overridden", "Accepted"],
  ["", "All"],
];

export default function InvoiceMatching() {
  const { can } = useAuth();
  const canConfigure = can(PERMISSIONS.organizationSettings);

  const [state, setState] = useState("exceptions");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState(null);
  const [tuning, setTuning] = useState(false);

  const load = useCallback(() => {
    let active = true;
    setLoading(true);
    const params = new URLSearchParams({ page: String(page), pageSize: "25" });
    if (state) params.set("state", state);
    if (query.trim()) params.set("q", query.trim());
    api
      .get(`/api/matching/invoices?${params}`)
      .then(({ data: body }) => active && setData(body))
      .catch(() => active && setData({ items: [], total: 0 }))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [page, state, query]);

  useEffect(() => {
    const timer = setTimeout(load, query ? 300 : 0);
    return () => clearTimeout(timer);
  }, [load, query]);

  useEffect(() => {
    let active = true;
    api
      .get("/api/matching/summary")
      .then(({ data: body }) => active && setSummary(body))
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [data]);

  const rows = data?.items ?? [];
  const pageSize = data?.pageSize ?? 25;
  const pages = Math.max(1, Math.ceil((data?.total ?? 0) / pageSize));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-white">
            Invoice matching
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Every invoice checked against the order it bills — prices,
            quantities, taxes and totals.
          </p>
        </div>
        {canConfigure && (
          <Button variant="secondary" onClick={() => setTuning((v) => !v)}>
            <Settings2 size={16} /> Tolerances
          </Button>
        )}
      </div>

      {tuning && canConfigure && (
        <ToleranceForm onClose={() => setTuning(false)} onSaved={load} />
      )}

      {summary && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {/* Leads with what somebody has to act on. "47 matched" is
              reassuring and useless. */}
          <Tile
            label="Must not be paid"
            value={summary.blocked}
            tone={summary.blocked > 0 ? "rose" : "muted"}
            hint="A blocking discrepancy nobody has accepted"
            onClick={() => {
              setState("blocked");
              setPage(1);
            }}
          />
          <Tile
            label="No purchase order"
            value={summary.unmatched}
            tone={summary.unmatched > 0 ? "amber" : "muted"}
            hint="Not linked to an order"
            onClick={() => {
              setState("unmatched");
              setPage(1);
            }}
          />
          <Tile
            label="Awaiting confirmation"
            value={summary.awaitingConfirmation}
            tone="muted"
            hint="A suggested link nobody has checked"
          />
          <Tile
            label="Matched"
            value={summary.byOutcome?.matched ?? 0}
            tone="muted"
            hint={`of ${summary.invoices} invoice${summary.invoices === 1 ? "" : "s"}`}
          />
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-[240px] max-w-sm flex-1">
          <Search
            size={16}
            className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500"
          />
          <input
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setPage(1);
            }}
            placeholder="Search invoice number or supplier…"
            className="h-11 w-full rounded-xl border border-white/10 bg-ink-900/60 pl-10 pr-3.5 text-sm text-white placeholder:text-slate-600 outline-none focus:border-brand-400/60 focus:ring-2 focus:ring-brand-400/20"
          />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {FILTERS.map(([value, label]) => (
            <button
              key={value || "all"}
              onClick={() => {
                setState(value);
                setPage(1);
              }}
              className={cn(
                "h-9 rounded-lg px-3 text-sm transition-colors",
                state === value
                  ? "bg-brand-500/15 text-brand-200"
                  : "text-slate-400 hover:bg-white/[0.06] hover:text-white",
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {loading && data === null ? (
        <div className="grid place-items-center py-20">
          <Loader2 className="animate-spin text-brand-400" size={26} />
        </div>
      ) : rows.length === 0 ? (
        <div className="glass flex flex-col items-center rounded-2xl px-6 py-16 text-center">
          <span className="grid h-14 w-14 place-items-center rounded-2xl bg-white/[0.04] text-slate-500">
            <GitCompareArrows size={26} />
          </span>
          <h3 className="mt-5 text-lg font-semibold text-white">
            {state === "exceptions" || state === "blocked"
              ? "Nothing needs attention"
              : query
                ? "Nothing matches that"
                : "No invoices yet"}
          </h3>
          <p className="mt-1.5 max-w-sm text-sm text-slate-400">
            {state === "exceptions" || state === "blocked"
              ? "Every invoice either matches its order or has been accepted by someone."
              : "Upload an invoice and it will be checked against your open orders automatically."}
          </p>
        </div>
      ) : (
        <div className={cn("glass overflow-hidden rounded-2xl", loading && "opacity-60")}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-sm">
              <thead>
                <tr className="border-b border-white/[0.06] text-left text-xs uppercase tracking-wider text-slate-500">
                  <th className="px-5 py-3.5 font-medium">Invoice</th>
                  <th className="px-4 py-3.5 font-medium">Supplier</th>
                  <th className="px-4 py-3.5 font-medium">Order</th>
                  <th className="px-4 py-3.5 font-medium">Result</th>
                  <th className="px-4 py-3.5 text-right font-medium">Amount</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.05]">
                {rows.map((row) => (
                  <tr
                    key={row.extractionId}
                    className="transition-colors hover:bg-white/[0.02]"
                  >
                    <td className="px-5 py-3.5">
                      <Link
                        to={`/dashboard/extractions/${row.extractionId}`}
                        className="font-medium text-white hover:text-brand-200"
                      >
                        {row.invoiceNumber || row.fileName}
                      </Link>
                      <div className="mt-0.5 text-xs text-slate-500">
                        {row.invoiceDate
                          ? formatDate(row.invoiceDate)
                          : formatDate(row.createdAt)}
                      </div>
                    </td>
                    <td className="max-w-[14rem] truncate px-4 py-3.5 text-slate-300">
                      {row.supplierName || row.vendorName || "—"}
                    </td>
                    <td className="px-4 py-3.5">
                      {row.match?.purchaseOrderId ? (
                        <>
                          <Link
                            to={`/dashboard/purchase-orders/${row.match.purchaseOrderId}`}
                            className="text-indigo-300 hover:text-indigo-200"
                          >
                            {row.match.poNumber}
                          </Link>
                          <div className="mt-0.5 text-xs text-slate-500">
                            {poStatusLabel(row.match.poStatus)}
                          </div>
                        </>
                      ) : (
                        <span className="text-xs text-slate-500">None</span>
                      )}
                    </td>
                    <td className="px-4 py-3.5">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <MatchOutcomeBadge
                          outcome={row.match?.outcome}
                          overridden={row.match?.overridden}
                        />
                        {row.match?.blockingCount > 0 && !row.match?.overridden && (
                          <span
                            className="inline-flex items-center gap-1 text-xs text-rose-300"
                            title="Blocking findings"
                          >
                            <ShieldAlert size={11} /> {row.match.blockingCount}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3.5 text-right tabular-nums text-slate-200">
                      {formatMoney(row.total, row.currency)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {pages > 1 && (
            <div className="flex items-center justify-between border-t border-white/[0.06] px-5 py-3 text-xs text-slate-400">
              <span>
                Page {page} of {pages} · {data.total} invoice
                {data.total === 1 ? "" : "s"}
              </span>
              <div className="flex gap-1">
                <button
                  disabled={page <= 1}
                  onClick={() => setPage((value) => value - 1)}
                  className="grid h-7 w-7 place-items-center rounded-md border border-white/10 disabled:opacity-40"
                  aria-label="Previous page"
                >
                  <ChevronLeft size={14} />
                </button>
                <button
                  disabled={page >= pages}
                  onClick={() => setPage((value) => value + 1)}
                  className="grid h-7 w-7 place-items-center rounded-md border border-white/10 disabled:opacity-40"
                  aria-label="Next page"
                >
                  <ChevronRight size={14} />
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Tile({ label, value, hint, tone, onClick }) {
  const tones = {
    rose: "border-rose-500/30 bg-rose-500/[0.07]",
    amber: "border-amber-500/30 bg-amber-500/[0.07]",
    muted: "border-white/[0.06] bg-white/[0.02]",
  };
  const Element = onClick ? "button" : "div";
  return (
    <Element
      {...(onClick ? { type: "button", onClick } : {})}
      className={cn(
        "rounded-2xl border p-4 text-left",
        tones[tone] ?? tones.muted,
        onClick && "transition-colors hover:bg-white/[0.05]",
      )}
    >
      <div className="text-xs uppercase tracking-wider text-slate-500">{label}</div>
      <div className="mt-1.5 text-2xl font-semibold tabular-nums text-white">
        {value ?? 0}
      </div>
      <div className="mt-0.5 text-xs text-slate-500">{hint}</div>
    </Element>
  );
}

/**
 * The tolerances, as a form.
 *
 * Both bounds for each figure are shown together because that is how they
 * work: a difference passes if it is inside EITHER. Showing only one would
 * make the other look inactive.
 */
const FIELDS = [
  {
    title: "Unit price",
    help: "A price is quoted and agreed, so it has no physical reason to vary. The default allows rounding only.",
    percent: "priceTolerancePercent",
    amount: "priceToleranceAmount",
  },
  {
    title: "Quantity",
    help: "Leave at zero to catch every over-delivery. Raise it if you buy by weight or volume.",
    percent: "quantityTolerancePercent",
    amount: "quantityToleranceAmount",
  },
  {
    title: "Invoice total",
    help: "Measured against what is left on the order, not the order's full value.",
    percent: "totalTolerancePercent",
    amount: "totalToleranceAmount",
  },
];

const FLAGS = [
  {
    key: "requirePoReference",
    title: "Every invoice must cite a purchase order",
    help: "Off by default: utilities, rent and expenses legitimately have none.",
  },
  {
    key: "blockUnapprovedPo",
    title: "Block invoices against unapproved orders",
    help: "The control that stops spend being authorized after it was incurred.",
  },
  {
    key: "autoConfirmExact",
    title: "Link automatically on an exact PO number",
    help: "Only when the comparison is clean as well. This confirms the link, never the payment.",
  },
];

function ToleranceForm({ onClose, onSaved }) {
  const [settings, setSettings] = useState(null);
  const [fields, setFields] = useState({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let active = true;
    api
      .get("/api/matching/settings")
      .then(({ data }) => active && setSettings(data.settings))
      .catch((err) => active && setError(apiError(err, "Couldn't load tolerances.")));
    return () => {
      active = false;
    };
  }, []);

  async function save(event) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setFields({});
    try {
      const { data } = await api.put("/api/matching/settings", settings);
      setSettings(data.settings);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
      onSaved?.();
    } catch (err) {
      setFields(err?.response?.data?.fields ?? {});
      setError(apiError(err, "Couldn't save those tolerances."));
    } finally {
      setSaving(false);
    }
  }

  function set(key, value) {
    setSettings((current) => ({ ...current, [key]: value }));
  }

  if (!settings) {
    return (
      <div className="glass rounded-2xl p-6">
        {error ? (
          <p className="text-sm text-rose-300">{error}</p>
        ) : (
          <Loader2 className="animate-spin text-brand-400" size={20} />
        )}
      </div>
    );
  }

  return (
    <form onSubmit={save} className="glass space-y-5 rounded-2xl p-5 sm:p-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-white">Matching tolerances</h2>
          <p className="mt-1 text-sm text-slate-400">
            A difference passes if it is within <em>either</em> bound. Leave one
            at zero to use the other alone.
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="text-slate-500 transition-colors hover:text-slate-300"
          aria-label="Close"
        >
          <X size={16} />
        </button>
      </div>

      <div className="space-y-4">
        {FIELDS.map((field) => (
          <div key={field.title} className="rounded-xl border border-white/[0.06] p-4">
            <div className="text-sm font-medium text-white">{field.title}</div>
            <p className="mt-0.5 text-xs text-slate-500">{field.help}</p>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <NumberField
                label="Percentage"
                suffix="%"
                value={settings[field.percent]}
                error={fields[field.percent]}
                onChange={(value) => set(field.percent, value)}
              />
              <NumberField
                label="Fixed amount"
                value={settings[field.amount]}
                error={fields[field.amount]}
                onChange={(value) => set(field.amount, value)}
              />
            </div>
          </div>
        ))}
      </div>

      <div className="space-y-2">
        {FLAGS.map((flag) => (
          <label
            key={flag.key}
            className="flex cursor-pointer items-start gap-3 rounded-xl border border-white/[0.06] p-3.5"
          >
            <input
              type="checkbox"
              checked={Boolean(settings[flag.key])}
              onChange={(event) => set(flag.key, event.target.checked)}
              className="mt-0.5 size-4 shrink-0 rounded border-white/20 bg-ink-900 accent-brand-500"
            />
            <span className="min-w-0">
              <span className="block text-sm text-white">{flag.title}</span>
              <span className="mt-0.5 block text-xs text-slate-500">{flag.help}</span>
            </span>
          </label>
        ))}
      </div>

      {error && <p className="text-sm text-rose-300">{error}</p>}

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={saving}>
          {saving && <Loader2 size={15} className="animate-spin" />}
          Save tolerances
        </Button>
        {saved && <span className="text-xs text-emerald-300">Saved</span>}
      </div>
    </form>
  );
}

function NumberField({ label, suffix, value, error, onChange }) {
  return (
    <label className="block">
      <span className="text-xs text-slate-400">{label}</span>
      <div className="relative mt-1">
        <input
          value={value ?? ""}
          onChange={(event) => onChange(event.target.value)}
          inputMode="decimal"
          className={cn(
            "h-10 w-full rounded-lg border bg-ink-950/60 px-3 text-sm tabular-nums text-white outline-none focus:ring-2 focus:ring-brand-400/20",
            error
              ? "border-rose-500/50 focus:border-rose-400/60"
              : "border-white/10 focus:border-brand-400/60",
            suffix && "pr-8",
          )}
        />
        {suffix && (
          <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-500">
            {suffix}
          </span>
        )}
      </div>
      {error && <span className="mt-1 block text-xs text-rose-300">{error}</span>}
    </label>
  );
}
