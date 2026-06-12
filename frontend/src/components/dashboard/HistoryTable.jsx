import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Search, FileText, Receipt, Landmark, Download, Sheet, Trash2, Eye, Inbox, AlertCircle, Loader2 } from "lucide-react";

const DOC_META = {
  receipt: { label: "Receipt", Icon: Receipt },
  statement: { label: "Statement", Icon: Landmark },
};
import { Button } from "@/components/ui/Button";
import { cn, formatDate, formatMoney } from "@/lib/utils";
import { api, downloadFile } from "@/lib/api";

export function HistoryTable({ initialItems }) {
  const [items, setItems] = useState(initialItems);
  const [q, setQ] = useState("");
  const [deleting, setDeleting] = useState(null);

  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase();
    if (!term) return items;
    return items.filter((it) =>
      [it.vendorName, it.invoiceNumber, it.fileName]
        .filter(Boolean)
        .some((v) => v.toLowerCase().includes(term)),
    );
  }, [items, q]);

  async function remove(id) {
    if (!confirm("Delete this extraction? This cannot be undone.")) return;
    setDeleting(id);
    try {
      await api.delete(`/api/extractions/${id}`);
      setItems((prev) => prev.filter((it) => it.id !== id));
    } catch {
      /* ignore */
    }
    setDeleting(null);
  }

  if (items.length === 0) {
    return (
      <div className="glass flex flex-col items-center justify-center rounded-2xl px-6 py-20 text-center">
        <span className="grid h-14 w-14 place-items-center rounded-2xl bg-white/[0.04] text-slate-500">
          <Inbox size={26} />
        </span>
        <h3 className="mt-5 text-lg font-semibold text-white">No extractions yet</h3>
        <p className="mt-1.5 max-w-xs text-sm text-slate-400">
          Process your first invoice, receipt or statement and it'll show up here.
        </p>
        <Button to="/dashboard" className="mt-6">
          Extract a document
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="relative max-w-sm">
        <Search size={16} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search vendor, invoice #, file…"
          className="h-11 w-full rounded-xl border border-white/10 bg-ink-900/60 pl-10 pr-3.5 text-sm text-white placeholder:text-slate-600 outline-none focus:border-brand-400/60 focus:ring-2 focus:ring-brand-400/20"
        />
      </div>

      <div className="glass overflow-hidden rounded-2xl">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[680px] text-sm">
            <thead>
              <tr className="border-b border-white/[0.06] text-left text-xs uppercase tracking-wider text-slate-500">
                <th className="px-5 py-3.5 font-medium">Vendor / File</th>
                <th className="px-4 py-3.5 font-medium">Invoice #</th>
                <th className="px-4 py-3.5 font-medium">Date</th>
                <th className="px-4 py-3.5 text-right font-medium">Total</th>
                <th className="px-4 py-3.5 font-medium">Status</th>
                <th className="px-4 py-3.5 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.05]">
              {filtered.map((it) => {
                const completed = it.status === "completed";
                const processing = it.status === "processing";
                const failed = !completed && !processing;
                return (
                  <tr key={it.id} className="group transition-colors hover:bg-white/[0.02]">
                    <td className="px-5 py-3.5">
                      {(() => {
                        const meta = DOC_META[it.docType];
                        const Icon = meta?.Icon || FileText;
                        return (
                          <div className="flex items-center gap-3">
                            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-brand-500/12 text-brand-300">
                              <Icon size={15} />
                            </span>
                            <div className="min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="truncate font-medium text-white">{it.vendorName || "Unknown vendor"}</span>
                                {meta && (
                                  <span className="shrink-0 rounded-full bg-white/[0.06] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                                    {meta.label}
                                  </span>
                                )}
                              </div>
                              <div className="truncate text-xs text-slate-500">{it.fileName}</div>
                            </div>
                          </div>
                        );
                      })()}
                    </td>
                    <td className="px-4 py-3.5 text-slate-300">{it.invoiceNumber || "—"}</td>
                    <td className="px-4 py-3.5 text-slate-400">{formatDate(it.invoiceDate || it.createdAt)}</td>
                    <td className="px-4 py-3.5 text-right font-medium text-white tabular-nums">
                      {formatMoney(it.total, it.currency)}
                    </td>
                    <td className="px-4 py-3.5">
                      <span
                        className={cn(
                          "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium",
                          processing
                            ? "bg-amber-500/15 text-amber-300"
                            : failed
                              ? "bg-red-500/15 text-red-300"
                              : "bg-emerald-500/15 text-emerald-300",
                        )}
                      >
                        {processing ? <Loader2 size={12} className="animate-spin" /> : failed ? <AlertCircle size={12} /> : null}
                        {processing ? "Processing" : failed ? "Failed" : "Completed"}
                      </span>
                    </td>
                    <td className="px-4 py-3.5">
                      <div className="flex items-center justify-end gap-1">
                        {completed && (
                          <>
                            <Link
                              to={`/dashboard/extractions/${it.id}`}
                              className="grid h-8 w-8 place-items-center rounded-lg text-slate-400 transition-colors hover:bg-white/[0.06] hover:text-white"
                              title="View"
                            >
                              <Eye size={15} />
                            </Link>
                            <button
                              onClick={() =>
                                downloadFile(
                                  `/api/extractions/${it.id}/csv`,
                                  `${it.invoiceNumber || it.vendorName || "invoice"}.csv`,
                                )
                              }
                              className="grid h-8 w-8 place-items-center rounded-lg text-slate-400 transition-colors hover:bg-white/[0.06] hover:text-white"
                              title="Download CSV"
                            >
                              <Download size={15} />
                            </button>
                            <button
                              onClick={() =>
                                downloadFile(
                                  `/api/extractions/${it.id}/xlsx`,
                                  `${it.invoiceNumber || it.vendorName || "invoice"}.xlsx`,
                                )
                              }
                              className="grid h-8 w-8 place-items-center rounded-lg text-slate-400 transition-colors hover:bg-white/[0.06] hover:text-white"
                              title="Download Excel"
                            >
                              <Sheet size={15} />
                            </button>
                          </>
                        )}
                        <button
                          onClick={() => remove(it.id)}
                          disabled={deleting === it.id}
                          className="grid h-8 w-8 place-items-center rounded-lg text-slate-400 transition-colors hover:bg-red-500/15 hover:text-red-300 disabled:opacity-50"
                          title="Delete"
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-5 py-10 text-center text-sm text-slate-500">
                    No results for “{q}”.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
