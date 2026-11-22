import { useState } from "react";
import { Copy, Check, X, Loader2, ExternalLink } from "lucide-react";
import { Link } from "react-router-dom";
import { api, apiError } from "@/lib/api";
import { formatMoney } from "@/lib/utils.js";

/**
 * Suspected duplicates of the document being viewed.
 *
 * Nothing here deletes or blocks anything. A supplier can legitimately bill the
 * same amount twice in a day, so the user decides: "Yes, duplicate" records the
 * finding, "Not a duplicate" dismisses it permanently so the same warning stops
 * nagging on every page load.
 */

const REASON_LABEL = {
  exact_file: "Identical file",
  same_number: "Same supplier & invoice number",
  same_amount_date: "Same supplier, amount & date",
  similar: "Looks similar",
};

function strength(score) {
  if (score >= 0.95) return { label: "Almost certain", tone: "text-rose-300" };
  if (score >= 0.75) return { label: "Likely", tone: "text-amber-300" };
  return { label: "Possible", tone: "text-sky-300" };
}

export function DuplicateWarning({ extractionId, duplicates, onResolved }) {
  const [items, setItems] = useState(duplicates ?? []);
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState(null);

  if (!items.length) return null;

  async function resolve(matchId, status) {
    setBusyId(matchId);
    setError(null);
    try {
      const { data } = await api.post(
        `/api/extractions/${extractionId}/duplicates/${matchId}`,
        { status },
      );
      setItems(data.duplicates ?? []);
      onResolved?.(data.duplicates ?? []);
    } catch (err) {
      setError(apiError(err, "Couldn't save that decision."));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-4">
      <div className="flex items-start gap-3">
        <Copy size={18} className="mt-0.5 shrink-0 text-rose-400" />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-rose-200">
            {items.length === 1
              ? "This may already have been uploaded"
              : `${items.length} possible duplicates found`}
          </div>
          <p className="mt-0.5 text-xs text-rose-200/80">
            Check before approving payment. Nothing has been deleted or rejected.
          </p>

          <ul className="mt-3 space-y-3">
            {items.map((item) => {
              const match = item.match ?? {};
              const level = strength(item.score);
              const busy = busyId === item.id;
              return (
                <li
                  key={item.id}
                  className="rounded-lg border border-white/10 bg-ink-950/40 p-3"
                >
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
                    <span className={`font-semibold ${level.tone}`}>{level.label}</span>
                    <span className="text-slate-500">·</span>
                    <span className="text-slate-300">
                      {REASON_LABEL[item.reason] ?? item.reason}
                    </span>
                  </div>

                  <p className="mt-1.5 text-xs leading-relaxed text-slate-200">
                    {item.detail}
                  </p>

                  {match.id && (
                    <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-400">
                      <span className="truncate font-medium text-slate-300">
                        {match.fileName}
                      </span>
                      {match.invoiceNumber && <span>#{match.invoiceNumber}</span>}
                      {match.total && (
                        <span className="tabular-nums">
                          {formatMoney(match.total, match.currency)}
                        </span>
                      )}
                      <Link
                        to={`/dashboard/extractions/${match.id}`}
                        className="inline-flex items-center gap-1 text-indigo-300 hover:text-indigo-200"
                      >
                        Compare <ExternalLink size={11} />
                      </Link>
                    </div>
                  )}

                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => resolve(item.id, "confirmed")}
                      className="inline-flex items-center gap-1.5 rounded-md border border-rose-400/40 bg-rose-500/15 px-2.5 py-1 text-xs font-medium text-rose-200 hover:bg-rose-500/25 disabled:opacity-50"
                    >
                      {busy ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
                      Yes, duplicate
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => resolve(item.id, "dismissed")}
                      className="inline-flex items-center gap-1.5 rounded-md border border-white/15 px-2.5 py-1 text-xs font-medium text-slate-300 hover:bg-white/5 disabled:opacity-50"
                    >
                      <X size={12} /> Not a duplicate
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>

          {error && <p className="mt-2 text-xs text-rose-300">{error}</p>}
        </div>
      </div>
    </div>
  );
}
