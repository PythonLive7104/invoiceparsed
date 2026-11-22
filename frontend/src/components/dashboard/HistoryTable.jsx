import { useState } from "react";
import { Link } from "react-router-dom";
import { FileText, Receipt, Landmark, Download, Sheet, Trash2, Eye, Inbox, AlertCircle, Loader2, Copy } from "lucide-react";

const DOC_META = {
  receipt: { label: "Receipt", Icon: Receipt },
  statement: { label: "Statement", Icon: Landmark },
};
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { cn, formatDate, formatMoney } from "@/lib/utils";
import { api, downloadFile } from "@/lib/api";
import { ValidationBadge } from "@/components/dashboard/ValidationPanel";

/** The list row carries a flat status + count; the badge wants the object. */
function validationOf(it) {
  if (!it.validationStatus) return null;
  return { status: it.validationStatus, issueCount: it.issueCount ?? 0 };
}

/**
 * Processing history rows.
 *
 * Controlled: filtering, searching and paging all happen on the server, so this
 * renders exactly what it is given. It used to filter a fixed array in the
 * browser, which only ever worked because the API returned at most 300 rows -
 * anything older was invisible and unsearchable.
 */
export function HistoryTable({ items, emptyState = "none", onChanged }) {
  const [toDelete, setToDelete] = useState(null); // item pending confirmation
  const [deleting, setDeleting] = useState(false);

  async function confirmDelete() {
    if (!toDelete) return;
    setDeleting(true);
    try {
      await api.delete(`/api/extractions/${toDelete.id}`);
      setToDelete(null);
      onChanged?.();
    } catch {
      /* ignore */
    }
    setDeleting(false);
  }

  // "none" means the organization has no documents at all; "filtered" means the
  // current filters matched nothing. Telling those apart stops a filtered view
  // from looking like an empty account.
  if (items.length === 0 && emptyState === "none") {
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
                <th className="px-4 py-3.5 font-medium">Checks</th>
                <th className="px-4 py-3.5 font-medium">Uploaded by</th>
                <th className="px-4 py-3.5 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.05]">
              {items.map((it) => {
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
                      {failed && it.errorMessage && (
                        <div className="mt-1 max-w-[220px] truncate text-xs text-red-300/80" title={it.errorMessage}>
                          {it.errorMessage}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3.5">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <ValidationBadge validation={validationOf(it)} />
                        {it.duplicateCount > 0 && (
                          <span
                            className="inline-flex items-center gap-1 rounded-full border border-rose-500/30 bg-rose-500/10 px-2 py-0.5 text-xs font-medium text-rose-300"
                            title="Possible duplicate of another document"
                          >
                            <Copy size={11} /> {it.duplicateCount}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3.5 text-xs text-slate-400">
                      <div className="truncate">{it.uploadedBy || "—"}</div>
                      {it.processingMs ? (
                        <div className="text-slate-600">{(it.processingMs / 1000).toFixed(1)}s</div>
                      ) : null}
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
                          onClick={() => setToDelete(it)}
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
              {items.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-5 py-10 text-center text-sm text-slate-500">
                    Nothing matches these filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <ConfirmDialog
        open={!!toDelete}
        title="Delete this extraction?"
        description={
          toDelete
            ? `“${toDelete.vendorName || toDelete.fileName || "This document"}” and its uploaded files will be permanently removed. This can't be undone.`
            : ""
        }
        confirmLabel="Delete"
        loading={deleting}
        onConfirm={confirmDelete}
        onClose={() => !deleting && setToDelete(null)}
      />
    </div>
  );
}
