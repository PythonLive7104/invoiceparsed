import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Search, Plus, Building2, Loader2, Users, AlertTriangle, ChevronLeft, ChevronRight, X,
} from "lucide-react";
import { api, apiError } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth.jsx";
import {
  PAYABLES,
  PAYABLES_COPY,
  UpgradePanel,
} from "@/components/dashboard/UpgradePanel";

/**
 * Suppliers.
 *
 * Most records here create themselves: uploading an invoice attaches it to a
 * supplier, creating one if the vendor is new. The manual form is for adding a
 * supplier before their first invoice arrives.
 */
export default function Suppliers() {
  const { has } = useAuth();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("active");
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [duplicates, setDuplicates] = useState([]);
  const [creating, setCreating] = useState(false);

  // A locked plan gets the upgrade panel below instead of the list, so
  // nothing here should go to the server: every payables endpoint would
  // answer 402. Short-circuited inside the loaders rather than before the
  // hooks, because skipping a hook would change the hook order.
  const locked = !has(PAYABLES);

  const load = useCallback(() => {
    if (locked) return undefined;
    let active = true;
    setLoading(true);
    const params = new URLSearchParams({ status, page: String(page), perPage: "25" });
    if (query.trim()) params.set("q", query.trim());
    api
      .get(`/api/suppliers?${params}`)
      .then(({ data: body }) => active && setData(body))
      .catch(() => active && setData({ suppliers: [], total: 0, pages: 1 }))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [query, status, page, locked]);

  useEffect(() => {
    const timer = setTimeout(load, 250);   // debounce typing in the search box
    return () => clearTimeout(timer);
  }, [load]);

  useEffect(() => {
    if (locked) return;
    api
      .get("/api/suppliers/duplicates")
      .then(({ data: body }) => setDuplicates(body.duplicates ?? []))
      .catch(() => setDuplicates([]));
  }, [locked]);

  const rows = data?.suppliers ?? [];
  const pages = data?.pages ?? 1;

  // Rendered instead of the list. An early return of JSX below every
  // hook, so the hook order never changes.
  if (locked)
    return <UpgradePanel {...PAYABLES_COPY.suppliers} icon={Building2} />;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-white sm:text-3xl">
            Suppliers
          </h1>
          <p className="mt-1.5 text-slate-400">
            {data?.total
              ? `${data.total} supplier${data.total === 1 ? "" : "s"}.`
              : "Created automatically as invoices arrive."}
          </p>
        </div>
        <Button onClick={() => setCreating(true)}>
          <Plus size={16} /> Add supplier
        </Button>
      </div>

      {duplicates.length > 0 && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle size={17} className="mt-0.5 shrink-0 text-amber-400" />
            <div className="min-w-0 text-sm">
              <div className="font-semibold text-amber-200">
                {duplicates.length} possible duplicate supplier
                {duplicates.length === 1 ? "" : "s"}
              </div>
              <ul className="mt-1.5 space-y-1 text-xs text-amber-100/80">
                {duplicates.slice(0, 4).map((d, i) => (
                  <li key={i}>{d.detail}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-[240px] flex-1 max-w-sm">
          <Search size={16} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(1);
            }}
            placeholder="Search name, email or tax ID…"
            className="h-11 w-full rounded-xl border border-white/10 bg-ink-900/60 pl-10 pr-3.5 text-sm text-white placeholder:text-slate-600 outline-none focus:border-brand-400/60 focus:ring-2 focus:ring-brand-400/20"
          />
        </div>
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setPage(1);
          }}
          className="h-11 rounded-xl border border-white/10 bg-ink-900/60 px-3 text-sm text-white outline-none focus:border-brand-400/60"
        >
          <option value="active">Active</option>
          <option value="archived">Archived</option>
          <option value="all">All</option>
        </select>
      </div>

      {loading && data === null ? (
        <div className="grid place-items-center py-20">
          <Loader2 className="animate-spin text-brand-400" size={26} />
        </div>
      ) : rows.length === 0 ? (
        <div className="glass flex flex-col items-center rounded-2xl px-6 py-16 text-center">
          <span className="grid h-14 w-14 place-items-center rounded-2xl bg-white/[0.04] text-slate-500">
            <Users size={26} />
          </span>
          <h3 className="mt-5 text-lg font-semibold text-white">
            {query ? "No suppliers match that" : "No suppliers yet"}
          </h3>
          <p className="mt-1.5 max-w-sm text-sm text-slate-400">
            {query
              ? "Try a different name, email or tax ID."
              : "Upload an invoice and we'll create the supplier automatically, or add one by hand."}
          </p>
        </div>
      ) : (
        <div className={cn("glass overflow-hidden rounded-2xl", loading && "opacity-60")}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="border-b border-white/[0.06] text-left text-xs uppercase tracking-wider text-slate-500">
                  <th className="px-5 py-3.5 font-medium">Supplier</th>
                  <th className="px-4 py-3.5 font-medium">Tax ID</th>
                  <th className="px-4 py-3.5 font-medium">Terms</th>
                  <th className="px-4 py-3.5 text-right font-medium">Invoices</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.05]">
                {rows.map((s) => (
                  <tr key={s.id} className="transition-colors hover:bg-white/[0.02]">
                    <td className="px-5 py-3.5">
                      <Link to={`/dashboard/suppliers/${s.id}`} className="flex items-center gap-3">
                        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-brand-500/12 text-brand-300">
                          <Building2 size={15} />
                        </span>
                        <span className="min-w-0">
                          <span className="block truncate font-medium text-white">{s.name}</span>
                          <span className="block truncate text-xs text-slate-500">
                            {s.email || s.address || "—"}
                          </span>
                        </span>
                      </Link>
                    </td>
                    <td className="px-4 py-3.5 text-slate-400">{s.taxId || "—"}</td>
                    <td className="px-4 py-3.5 text-slate-400">{s.paymentTerms || "—"}</td>
                    <td className="px-4 py-3.5 text-right tabular-nums text-slate-300">
                      {s.invoiceCount}
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
          <span className="text-slate-500">Page {page} of {pages}</span>
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

      {creating && (
        <NewSupplierDialog
          onClose={() => setCreating(false)}
          onCreated={() => {
            setCreating(false);
            load();
          }}
        />
      )}
    </div>
  );
}

function NewSupplierDialog({ onClose, onCreated }) {
  const [form, setForm] = useState({ name: "", email: "", taxId: "", paymentTerms: "" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [fields, setFields] = useState({});

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setFields({});
    try {
      await api.post("/api/suppliers", form);
      onCreated();
    } catch (err) {
      setFields(err?.response?.data?.fields ?? {});
      setError(apiError(err, "Couldn't create that supplier."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4">
      <form
        onSubmit={submit}
        className="glass w-full max-w-md rounded-2xl p-6"
      >
        <div className="flex items-start justify-between">
          <h2 className="text-lg font-semibold text-white">Add a supplier</h2>
          <button type="button" onClick={onClose} className="text-slate-500 hover:text-white">
            <X size={18} />
          </button>
        </div>

        <div className="mt-4 space-y-3">
          {[
            ["name", "Name", "Acme Supplies Ltd"],
            ["email", "Email", "ar@acme.example"],
            ["taxId", "Tax ID", "TIN-12345"],
            ["paymentTerms", "Payment terms", "Net 30"],
          ].map(([key, label, placeholder]) => (
            <label key={key} className="block">
              <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-500">
                {label}
              </span>
              <input
                value={form[key]}
                placeholder={placeholder}
                onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                className="h-10 w-full rounded-lg border border-white/10 bg-ink-900/60 px-3 text-sm text-white placeholder:text-slate-600 outline-none focus:border-brand-400/60"
              />
              {fields[key] && <span className="mt-1 block text-xs text-rose-300">{fields[key]}</span>}
            </label>
          ))}
        </div>

        {error && <p className="mt-3 text-xs text-rose-300">{error}</p>}

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="h-10 rounded-lg px-4 text-sm text-slate-300 hover:bg-white/[0.06]"
          >
            Cancel
          </button>
          <Button type="submit" disabled={saving || !form.name.trim()}>
            {saving ? <Loader2 size={15} className="animate-spin" /> : null} Create
          </Button>
        </div>
      </form>
    </div>
  );
}
