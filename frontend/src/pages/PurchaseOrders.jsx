import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Search, Plus, Loader2, ClipboardList, ChevronLeft, ChevronRight, X,
  AlertTriangle,
} from "lucide-react";
import { api, apiError } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { PoStatusBadge } from "@/components/dashboard/PoStatus";
import { cn, formatDate, formatMoney } from "@/lib/utils";
import { useAuth } from "@/lib/auth.jsx";
import { PERMISSIONS } from "@/lib/permissions";

/**
 * Purchase orders.
 *
 * The commitment side of payables: what the organization has agreed to buy.
 * The summary strip leads with what is waiting on a person, because an order
 * stuck in approval is the thing that actually costs money — the supplier is
 * not shipping while it sits there.
 */

const FILTERS = [
  ["", "All"],
  ["draft", "Draft"],
  ["pending_approval", "Awaiting approval"],
  ["open", "Open"],
  ["fully_received", "Received"],
  ["closed", "Closed"],
  ["cancelled", "Cancelled"],
];

export default function PurchaseOrders() {
  const { can } = useAuth();
  // Raising an order is a procurement capability; an accountant or viewer can
  // read the list but not add to it. The server refuses either way - this just
  // keeps a button from appearing that would answer 403.
  const canWrite = can(PERMISSIONS.purchaseOrdersWrite);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(() => {
    let active = true;
    setLoading(true);
    const params = new URLSearchParams({ page: String(page), perPage: "25" });
    if (status) params.set("status", status);
    if (query.trim()) params.set("q", query.trim());
    api
      .get(`/api/purchase-orders?${params}`)
      .then(({ data: body }) => active && setData(body))
      .catch(() => active && setData({ purchaseOrders: [], total: 0, pages: 1 }))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [query, status, page]);

  useEffect(() => {
    const timer = setTimeout(load, 250);   // debounce typing in the search box
    return () => clearTimeout(timer);
  }, [load]);

  const loadSummary = useCallback(() => {
    api
      .get("/api/purchase-orders/summary")
      .then(({ data: body }) => setSummary(body))
      .catch(() => setSummary(null));
  }, []);

  useEffect(loadSummary, [loadSummary]);

  const rows = data?.purchaseOrders ?? [];
  const pages = data?.pages ?? 1;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-white sm:text-3xl">
            Purchase orders
          </h1>
          <p className="mt-1.5 text-slate-400">
            What you have agreed to buy, and what is still outstanding.
          </p>
        </div>
        {canWrite && (
          <Button onClick={() => setCreating(true)}>
            <Plus size={16} /> New order
          </Button>
        )}
      </div>

      {summary?.awaitingApproval > 0 && (
        <button
          onClick={() => {
            setStatus("pending_approval");
            setPage(1);
          }}
          className="flex w-full items-start gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-left transition-colors hover:bg-amber-500/[0.14]"
        >
          <AlertTriangle size={17} className="mt-0.5 shrink-0 text-amber-400" />
          <div className="text-sm">
            <span className="font-semibold text-amber-200">
              {summary.awaitingApproval} order
              {summary.awaitingApproval === 1 ? "" : "s"} awaiting approval
            </span>
            <p className="mt-0.5 text-xs text-amber-100/70">
              Suppliers are not shipping while these sit here.
            </p>
          </div>
        </button>
      )}

      {summary?.openCommitment?.length > 0 && (
        <div className="flex flex-wrap gap-3">
          {summary.openCommitment.map((row) => (
            <div key={row.currency} className="glass rounded-xl px-4 py-3">
              <div className="text-xs uppercase tracking-wide text-slate-500">
                Committed · {row.currency}
              </div>
              <div className="mt-1 text-xl font-semibold tabular-nums text-white">
                {formatMoney(row.total, row.currency)}
              </div>
              <div className="text-xs text-slate-500">
                {row.count} open order{row.count === 1 ? "" : "s"}
              </div>
            </div>
          ))}
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
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(1);
            }}
            placeholder="Search PO number or reference…"
            className="h-11 w-full rounded-xl border border-white/10 bg-ink-900/60 pl-10 pr-3.5 text-sm text-white placeholder:text-slate-600 outline-none focus:border-brand-400/60 focus:ring-2 focus:ring-brand-400/20"
          />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {FILTERS.map(([value, label]) => (
            <button
              key={value || "all"}
              onClick={() => {
                setStatus(value);
                setPage(1);
              }}
              className={cn(
                "h-9 rounded-lg px-3 text-sm transition-colors",
                status === value
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
            <ClipboardList size={26} />
          </span>
          <h3 className="mt-5 text-lg font-semibold text-white">
            {query || status ? "Nothing matches that" : "No purchase orders yet"}
          </h3>
          <p className="mt-1.5 max-w-sm text-sm text-slate-400">
            {query || status
              ? "Try a different filter or search term."
              : "Raise an order to record what you have agreed to buy, then match arriving invoices against it."}
          </p>
          {!query && !status && canWrite && (
            <Button className="mt-6" onClick={() => setCreating(true)}>
              <Plus size={16} /> New order
            </Button>
          )}
        </div>
      ) : (
        <div className={cn("glass overflow-hidden rounded-2xl", loading && "opacity-60")}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <thead>
                <tr className="border-b border-white/[0.06] text-left text-xs uppercase tracking-wider text-slate-500">
                  <th className="px-5 py-3.5 font-medium">Order</th>
                  <th className="px-4 py-3.5 font-medium">Supplier</th>
                  <th className="px-4 py-3.5 font-medium">Status</th>
                  <th className="px-4 py-3.5 font-medium">Expected</th>
                  <th className="px-4 py-3.5 text-right font-medium">Total</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.05]">
                {rows.map((po) => (
                  <tr key={po.id} className="transition-colors hover:bg-white/[0.02]">
                    <td className="px-5 py-3.5">
                      <Link
                        to={`/dashboard/purchase-orders/${po.id}`}
                        className="block font-medium text-white hover:text-brand-200"
                      >
                        {po.poNumber}
                      </Link>
                      <span className="text-xs text-slate-500">
                        {po.reference || `${po.lineCount} line${po.lineCount === 1 ? "" : "s"}`}
                      </span>
                    </td>
                    <td className="px-4 py-3.5 text-slate-300">
                      {po.supplierName || "—"}
                    </td>
                    <td className="px-4 py-3.5">
                      <PoStatusBadge status={po.status} />
                    </td>
                    <td className="px-4 py-3.5 text-slate-400">
                      {po.expectedDeliveryDate ? formatDate(po.expectedDeliveryDate) : "—"}
                    </td>
                    <td className="px-4 py-3.5 text-right tabular-nums text-white">
                      {formatMoney(po.total, po.currency)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {pages > 1 && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-slate-500">
            Page {page} of {pages}
          </span>
          <div className="flex gap-2">
            <button
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
              className="inline-flex h-9 items-center gap-1 rounded-lg border border-white/10 px-3 text-slate-300 hover:bg-white/[0.06] disabled:opacity-40"
            >
              <ChevronLeft size={15} /> Previous
            </button>
            <button
              disabled={page >= pages}
              onClick={() => setPage((p) => p + 1)}
              className="inline-flex h-9 items-center gap-1 rounded-lg border border-white/10 px-3 text-slate-300 hover:bg-white/[0.06] disabled:opacity-40"
            >
              Next <ChevronRight size={15} />
            </button>
          </div>
        </div>
      )}

      {creating && <NewOrderDialog onClose={() => setCreating(false)} />}
    </div>
  );
}

/**
 * Creating an order needs a supplier, so this asks for one and nothing else:
 * lines, dates and terms are added on the detail page, where there is room for
 * a table. A short form that gets you to a draft beats a long one that has to
 * be right first time.
 */
function NewOrderDialog({ onClose }) {
  const navigate = useNavigate();
  const [suppliers, setSuppliers] = useState(null);
  const [supplierId, setSupplierId] = useState("");
  const [reference, setReference] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    api
      .get("/api/suppliers?status=active&perPage=100")
      .then(({ data }) => setSuppliers(data.suppliers ?? []))
      .catch(() => setSuppliers([]));
  }, []);

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const { data } = await api.post("/api/purchase-orders", {
        supplierId,
        reference: reference.trim() || undefined,
        lines: [],
      });
      navigate(`/dashboard/purchase-orders/${data.purchaseOrder.id}`);
    } catch (err) {
      setError(apiError(err, "Couldn't create that order."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4">
      <form onSubmit={submit} className="glass w-full max-w-md rounded-2xl p-6">
        <div className="flex items-start justify-between">
          <h2 className="text-lg font-semibold text-white">New purchase order</h2>
          <button type="button" onClick={onClose} className="text-slate-500 hover:text-white">
            <X size={18} />
          </button>
        </div>

        <label className="mt-5 block">
          <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-500">
            Supplier
          </span>
          {suppliers === null ? (
            <div className="flex h-10 items-center gap-2 text-sm text-slate-500">
              <Loader2 size={14} className="animate-spin" /> Loading suppliers…
            </div>
          ) : suppliers.length === 0 ? (
            <p className="text-sm text-slate-400">
              You have no active suppliers yet.{" "}
              <Link to="/dashboard/suppliers" className="text-brand-300 hover:text-brand-200">
                Add one first
              </Link>
              .
            </p>
          ) : (
            <select
              value={supplierId}
              onChange={(e) => setSupplierId(e.target.value)}
              className="h-10 w-full rounded-lg border border-white/10 bg-ink-900/60 px-3 text-sm text-white outline-none focus:border-brand-400/60"
            >
              <option value="">Choose a supplier…</option>
              {suppliers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          )}
        </label>

        <label className="mt-3 block">
          <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-500">
            Your reference <span className="normal-case text-slate-600">(optional)</span>
          </span>
          <input
            value={reference}
            onChange={(e) => setReference(e.target.value)}
            placeholder="REQ-2026-014"
            className="h-10 w-full rounded-lg border border-white/10 bg-ink-900/60 px-3 text-sm text-white placeholder:text-slate-600 outline-none focus:border-brand-400/60"
          />
        </label>

        <p className="mt-3 text-xs text-slate-500">
          The order starts as a draft. Add lines next, then submit it for approval.
        </p>

        {error && <p className="mt-3 text-xs text-rose-300">{error}</p>}

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="h-10 rounded-lg px-4 text-sm text-slate-300 hover:bg-white/[0.06]"
          >
            Cancel
          </button>
          <Button type="submit" disabled={saving || !supplierId}>
            {saving ? <Loader2 size={15} className="animate-spin" /> : null} Create draft
          </Button>
        </div>
      </form>
    </div>
  );
}
