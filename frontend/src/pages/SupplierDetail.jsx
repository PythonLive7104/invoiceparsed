import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft, Building2, Landmark, Loader2, Pencil, Save, X, Archive, ShieldAlert,
} from "lucide-react";
import { api, apiError } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { formatDate, formatMoney } from "@/lib/utils";

/**
 * One supplier: profile, spend and invoice history.
 *
 * Payment details are shown only when the API returns them. The server omits
 * the key entirely for roles without `suppliers:bank:read`, so the absence of
 * the section is itself the permission check - the client never has the data
 * to leak.
 */

const PROFILE_FIELDS = [
  ["name", "Name"],
  ["contactName", "Contact"],
  ["email", "Email"],
  ["phone", "Phone"],
  ["address", "Address"],
  ["country", "Country"],
  ["taxId", "Tax ID"],
  ["registrationNumber", "Reg. number"],
  ["paymentTerms", "Payment terms"],
  ["currency", "Currency"],
];

const BANK_FIELDS = [
  ["bankName", "Bank"],
  ["accountName", "Account name"],
  ["accountNumber", "Account number"],
  ["iban", "IBAN"],
  ["swift", "SWIFT/BIC"],
  ["sortCode", "Sort code"],
];

export default function SupplierDetail() {
  const { id } = useParams();
  const [supplier, setSupplier] = useState(null);
  const [invoices, setInvoices] = useState([]);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({});
  const [saving, setSaving] = useState(false);
  const [fieldErrors, setFieldErrors] = useState({});

  useEffect(() => {
    let active = true;
    api
      .get(`/api/suppliers/${id}`)
      .then(({ data }) => active && setSupplier(data.supplier))
      .catch(() => active && setError("Supplier not found."));
    api
      .get(`/api/suppliers/${id}/invoices`)
      .then(({ data }) => active && setInvoices(data.invoices ?? []))
      .catch(() => active && setInvoices([]));
    return () => {
      active = false;
    };
  }, [id]);

  function startEditing() {
    const next = {};
    for (const [key] of PROFILE_FIELDS) next[key] = supplier[key] ?? "";
    if (supplier.bankDetails) {
      next.bankDetails = { ...supplier.bankDetails };
    }
    setDraft(next);
    setFieldErrors({});
    setEditing(true);
  }

  async function save() {
    setSaving(true);
    setFieldErrors({});
    try {
      const { data } = await api.patch(`/api/suppliers/${id}`, draft);
      setSupplier(data.supplier);
      setEditing(false);
    } catch (err) {
      setFieldErrors(err?.response?.data?.fields ?? {});
      setError(apiError(err, "Couldn't save those changes."));
    } finally {
      setSaving(false);
    }
  }

  async function archive() {
    const { data } = await api.delete(`/api/suppliers/${id}`);
    setSupplier((s) => ({ ...s, status: data.supplier.status }));
  }

  if (error && !supplier) {
    return (
      <div className="glass rounded-2xl p-8 text-center">
        <h2 className="text-lg font-semibold text-white">{error}</h2>
      </div>
    );
  }
  if (!supplier) {
    return (
      <div className="grid place-items-center py-20">
        <Loader2 className="animate-spin text-brand-400" size={26} />
      </div>
    );
  }

  const stats = supplier.stats ?? { invoiceCount: 0, totalsByCurrency: [] };

  return (
    <div className="space-y-6">
      <Link
        to="/dashboard/suppliers"
        className="inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-white"
      >
        <ArrowLeft size={16} /> All suppliers
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="grid h-12 w-12 place-items-center rounded-xl bg-brand-500/12 text-brand-300">
            <Building2 size={22} />
          </span>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-white">
              {supplier.name}
            </h1>
            <p className="text-sm text-slate-500">
              {stats.invoiceCount} invoice{stats.invoiceCount === 1 ? "" : "s"}
              {supplier.status === "archived" && " · Archived"}
            </p>
          </div>
        </div>

        <div className="flex gap-2">
          {editing ? (
            <>
              <button
                onClick={() => setEditing(false)}
                className="inline-flex h-10 items-center gap-1.5 rounded-lg px-3 text-sm text-slate-300 hover:bg-white/[0.06]"
              >
                <X size={15} /> Cancel
              </button>
              <Button onClick={save} disabled={saving}>
                {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
                Save
              </Button>
            </>
          ) : (
            <>
              {supplier.status !== "archived" && (
                <button
                  onClick={archive}
                  className="inline-flex h-10 items-center gap-1.5 rounded-lg px-3 text-sm text-slate-400 hover:bg-white/[0.06] hover:text-white"
                  title="Archived suppliers keep their invoice history"
                >
                  <Archive size={15} /> Archive
                </button>
              )}
              <Button onClick={startEditing}>
                <Pencil size={15} /> Edit
              </Button>
            </>
          )}
        </div>
      </div>

      {stats.totalsByCurrency?.length > 0 && (
        <div className="flex flex-wrap gap-3">
          {stats.totalsByCurrency.map((t) => (
            <div key={t.currency} className="glass rounded-xl px-4 py-3">
              <div className="text-xs uppercase tracking-wide text-slate-500">
                Invoiced · {t.currency}
              </div>
              <div className="mt-1 text-xl font-semibold tabular-nums text-white">
                {formatMoney(t.total, t.currency)}
              </div>
              <div className="text-xs text-slate-500">{t.count} document{t.count === 1 ? "" : "s"}</div>
            </div>
          ))}
        </div>
      )}

      <div className="glass rounded-2xl p-5 sm:p-6">
        <h2 className="text-sm font-semibold text-white">Details</h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {PROFILE_FIELDS.map(([key, label]) => (
            <div key={key}>
              <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
                {label}
              </div>
              {editing ? (
                <>
                  <input
                    value={draft[key] ?? ""}
                    onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
                    className="mt-1 h-9 w-full rounded-lg border border-white/10 bg-ink-900/60 px-2.5 text-sm text-white outline-none focus:border-brand-400/60"
                  />
                  {fieldErrors[key] && (
                    <span className="mt-1 block text-xs text-rose-300">{fieldErrors[key]}</span>
                  )}
                </>
              ) : (
                <div className="mt-1 text-sm text-slate-200">{supplier[key] || "—"}</div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Present only when the server sent payment details, which it does only
          for roles holding suppliers:bank:read. */}
      {supplier.bankDetails ? (
        <div className="glass rounded-2xl border border-amber-500/20 p-5 sm:p-6">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-white">
            <Landmark size={15} className="text-amber-300" /> Payment details
          </h2>
          <p className="mt-1 flex items-start gap-1.5 text-xs text-amber-200/70">
            <ShieldAlert size={13} className="mt-0.5 shrink-0" />
            Verify any change against a known contact. Altered payment details are
            the most common invoice fraud.
          </p>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {BANK_FIELDS.map(([key, label]) => (
              <div key={key}>
                <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
                  {label}
                </div>
                {editing ? (
                  <input
                    value={draft.bankDetails?.[key] ?? ""}
                    onChange={(e) =>
                      setDraft((d) => ({
                        ...d,
                        bankDetails: { ...(d.bankDetails ?? {}), [key]: e.target.value },
                      }))
                    }
                    className="mt-1 h-9 w-full rounded-lg border border-white/10 bg-ink-900/60 px-2.5 font-mono text-sm text-white outline-none focus:border-brand-400/60"
                  />
                ) : (
                  <div className="mt-1 font-mono text-sm text-slate-200">
                    {supplier.bankDetails[key] || "—"}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="glass overflow-hidden rounded-2xl">
        <h2 className="border-b border-white/[0.06] px-5 py-4 text-sm font-semibold text-white">
          Invoices
        </h2>
        {invoices.length === 0 ? (
          <p className="px-5 py-10 text-center text-sm text-slate-500">
            No invoices from this supplier yet.
          </p>
        ) : (
          <table className="w-full min-w-[520px] text-sm">
            <tbody className="divide-y divide-white/[0.05]">
              {invoices.map((it) => (
                <tr key={it.id} className="transition-colors hover:bg-white/[0.02]">
                  <td className="px-5 py-3">
                    <Link to={`/dashboard/extractions/${it.id}`} className="text-white hover:text-brand-200">
                      {it.invoiceNumber || it.fileName}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-slate-400">
                    {formatDate(it.invoiceDate || it.createdAt)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-white">
                    {formatMoney(it.total, it.currency)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
