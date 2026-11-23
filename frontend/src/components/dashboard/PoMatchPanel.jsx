import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ClipboardList,
  ExternalLink,
  Link2,
  Loader2,
  ShieldAlert,
  Undo2,
  X,
} from "lucide-react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/lib/auth.jsx";
import { PERMISSIONS } from "@/lib/permissions";
import { cn, formatMoney } from "@/lib/utils";
import { poStatusLabel } from "@/components/dashboard/PoStatus";
import {
  FindingList,
  MATCH_METHOD,
  MatchOutcomeBadge,
} from "@/components/dashboard/MatchStatus";

/**
 * Where this invoice stands against its purchase order.
 *
 * Two care-points, both about not overstating what the screen knows:
 *
 * * Nothing is computed here. Every figure and every finding comes from the
 *   server, which recomputes them from the document and the order on each
 *   read. A browser-side opinion about whether an invoice over-bills an order
 *   would be a second answer to a question that has one.
 * * "Blocked" is the server's word, not a conclusion drawn from the finding
 *   list. The same field is what P2.5's approval engine will read, so the
 *   screen and the approval cannot disagree about whether this may be paid.
 */
export function PoMatchPanel({ extractionId, match: initial, onChanged }) {
  const { can } = useAuth();
  const canLink = can(PERMISSIONS.documentsWrite);
  const canAccept = can(PERMISSIONS.approvalsAct);

  const [state, setState] = useState(initial ?? null);
  const [loading, setLoading] = useState(!initial);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [picking, setPicking] = useState(false);
  const [accepting, setAccepting] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get(`/api/matching/invoices/${extractionId}`);
      setState(data);
      setError(null);
    } catch (err) {
      setError(apiError(err, "Couldn't load the purchase-order match."));
    } finally {
      setLoading(false);
    }
  }, [extractionId]);

  useEffect(() => {
    load();
  }, [load]);

  async function act(key, request) {
    setBusy(key);
    setError(null);
    try {
      const { data } = await request();
      setState(data);
      onChanged?.(data);
      setPicking(false);
      setAccepting(false);
    } catch (err) {
      setError(apiError(err, "That didn't work."));
    } finally {
      setBusy(null);
    }
  }

  if (loading) {
    return (
      <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <Loader2 size={13} className="animate-spin" /> Checking against purchase
          orders…
        </div>
      </div>
    );
  }

  if (!state) {
    return error ? (
      <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-xs text-rose-300">
        {error}
      </div>
    ) : null;
  }

  const comparison = state.comparison ?? {};
  const matched = Boolean(state.match && comparison.matched);
  const rejected = state.match?.status === "rejected";
  // Only while the comparison is actually against it. A rejected suggestion
  // still carries the order somebody said no to, and showing that chip under
  // "no purchase order" would read as a contradiction.
  const po = matched ? state.match?.purchaseOrder : null;
  const blocked = comparison.blocked === true;
  const overridden = state.match?.overridden === true;

  const tone = blocked
    ? "border-rose-500/30 bg-rose-500/[0.07]"
    : comparison.outcome === "discrepancy" || overridden
      ? "border-amber-500/30 bg-amber-500/[0.07]"
      : matched
        ? "border-emerald-500/25 bg-emerald-500/[0.06]"
        : "border-white/10 bg-white/[0.03]";

  return (
    <div className={cn("rounded-xl border p-4", tone)}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          {blocked ? (
            <ShieldAlert size={18} className="mt-0.5 shrink-0 text-rose-400" />
          ) : (
            <ClipboardList size={18} className="mt-0.5 shrink-0 text-slate-400" />
          )}
          <div className="min-w-0">
            <div className="text-sm font-semibold text-white">
              {blocked
                ? "Do not pay this yet"
                : matched && comparison.outcome === "matched"
                  ? "Matches its purchase order"
                  : matched
                    ? "Checked against its purchase order"
                    : rejected
                      ? "Suggested order was rejected"
                      : "No purchase order"}
            </div>
            {po ? (
              <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-400">
                <Link
                  to={`/dashboard/purchase-orders/${po.id}`}
                  className="inline-flex items-center gap-1 font-medium text-indigo-300 hover:text-indigo-200"
                >
                  {po.poNumber} <ExternalLink size={10} />
                </Link>
                <span>·</span>
                <span>{poStatusLabel(po.status)}</span>
                <span>·</span>
                <span className="tabular-nums">
                  {formatMoney(po.total, po.currency)}
                </span>
                {state.match?.method && (
                  <>
                    <span>·</span>
                    <span>
                      {MATCH_METHOD[state.match.method] ?? state.match.method}
                    </span>
                  </>
                )}
              </div>
            ) : (
              <p className="mt-0.5 text-xs text-slate-400">
                {rejected
                  ? `${state.match.purchaseOrder?.poNumber ?? "The suggested order"} was ruled out. Link this invoice to the right order.`
                  : comparison.reference
                    ? `The invoice cites ${comparison.reference}.`
                    : "This invoice does not reference one."}
              </p>
            )}
          </div>
        </div>

        <MatchOutcomeBadge
          outcome={matched ? comparison.outcome : null}
          overridden={overridden}
        />
      </div>

      {blocked && (
        <p className="mt-3 rounded-lg border border-rose-400/20 bg-rose-500/10 px-3 py-2 text-xs leading-relaxed text-rose-100">
          Something here must be resolved before payment. Nothing has been
          rejected — someone with approval authority can accept these
          discrepancies on the record instead.
        </p>
      )}

      <FindingList findings={comparison.findings} className="mt-3" />

      {matched && comparison.totals?.poTotal && (
        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 border-t border-white/10 pt-3 text-xs sm:grid-cols-4">
          <Figure label="Order" value={comparison.totals.poTotal}
            currency={comparison.totals.currency} />
          <Figure label="Already invoiced" value={comparison.totals.alreadyInvoiced}
            currency={comparison.totals.currency} />
          <Figure label="This invoice" value={comparison.totals.invoiceTotal}
            currency={comparison.totals.invoiceCurrency ?? comparison.totals.currency} />
          <Figure label="Left on the order" value={comparison.totals.remainingAfter}
            currency={comparison.totals.currency} />
        </dl>
      )}

      {overridden && (
        <div className="mt-3 rounded-lg border border-amber-400/20 bg-amber-500/[0.08] px-3 py-2 text-xs leading-relaxed text-amber-100">
          <span className="font-medium">Accepted by {state.match.overriddenBy}</span>
          {state.match.overrideNote && <>: “{state.match.overrideNote}”</>}
        </div>
      )}

      {error && <p className="mt-3 text-xs text-rose-300">{error}</p>}

      {/* ── Actions ── */}
      <div className="mt-3 flex flex-wrap gap-2">
        {canLink && (
          <button
            type="button"
            onClick={() => setPicking((v) => !v)}
            className="inline-flex items-center gap-1.5 rounded-md border border-white/15 px-2.5 py-1 text-xs font-medium text-slate-300 transition-colors hover:bg-white/5"
          >
            <Link2 size={12} />
            {matched ? "Change order" : "Link to an order"}
          </button>
        )}
        {canLink && state.match && (
          <>
            <button
              type="button"
              disabled={busy === "reject"}
              onClick={() =>
                act("reject", () =>
                  api.post(`/api/matching/invoices/${extractionId}/reject`),
                )
              }
              className="inline-flex items-center gap-1.5 rounded-md border border-white/15 px-2.5 py-1 text-xs font-medium text-slate-300 transition-colors hover:bg-white/5 disabled:opacity-50"
            >
              {busy === "reject" ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <X size={12} />
              )}
              Wrong order
            </button>
            <button
              type="button"
              disabled={busy === "unlink"}
              onClick={() =>
                act("unlink", () =>
                  api.delete(`/api/matching/invoices/${extractionId}`),
                )
              }
              className="inline-flex items-center gap-1.5 rounded-md border border-white/15 px-2.5 py-1 text-xs font-medium text-slate-400 transition-colors hover:bg-white/5 disabled:opacity-50"
            >
              <Undo2 size={12} /> Unlink
            </button>
          </>
        )}
        {canAccept && matched && !overridden &&
          (comparison.counts?.blocking > 0 || comparison.counts?.review > 0) && (
            <button
              type="button"
              onClick={() => setAccepting((v) => !v)}
              className="inline-flex items-center gap-1.5 rounded-md border border-amber-400/40 bg-amber-500/15 px-2.5 py-1 text-xs font-medium text-amber-100 transition-colors hover:bg-amber-500/25"
            >
              Accept these discrepancies
            </button>
          )}
        {canAccept && overridden && (
          <button
            type="button"
            disabled={busy === "withdraw"}
            onClick={() =>
              act("withdraw", () =>
                api.delete(`/api/matching/invoices/${extractionId}/override`),
              )
            }
            className="inline-flex items-center gap-1.5 rounded-md border border-white/15 px-2.5 py-1 text-xs font-medium text-slate-300 transition-colors hover:bg-white/5 disabled:opacity-50"
          >
            <Undo2 size={12} /> Withdraw acceptance
          </button>
        )}
      </div>

      {picking && (
        <CandidatePicker
          extractionId={extractionId}
          busy={busy === "link"}
          onPick={(purchaseOrderId) =>
            act("link", () =>
              api.post(`/api/matching/invoices/${extractionId}/link`, {
                purchaseOrderId,
              }),
            )
          }
          onClose={() => setPicking(false)}
        />
      )}

      {accepting && (
        <AcceptForm
          busy={busy === "accept"}
          onSubmit={(note) =>
            act("accept", () =>
              api.post(`/api/matching/invoices/${extractionId}/override`, { note }),
            )
          }
          onCancel={() => setAccepting(false)}
        />
      )}
    </div>
  );
}

function Figure({ label, value, currency }) {
  return (
    <div>
      <dt className="text-slate-500">{label}</dt>
      <dd className="tabular-nums text-slate-200">{formatMoney(value, currency)}</dd>
    </div>
  );
}

/**
 * The orders this invoice might belong to, as the server ranks them, plus a
 * search box for the case where it suggests nothing useful.
 */
function CandidatePicker({ extractionId, busy, onPick, onClose }) {
  const [suggested, setSuggested] = useState(null);
  const [term, setTerm] = useState("");
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;
    api
      .get(`/api/matching/invoices/${extractionId}/candidates`)
      .then(({ data }) => active && setSuggested(data.candidates ?? []))
      .catch((err) => active && setError(apiError(err, "Couldn't load suggestions.")));
    return () => {
      active = false;
    };
  }, [extractionId]);

  useEffect(() => {
    if (!term.trim()) {
      setResults(null);
      return undefined;
    }
    let active = true;
    const timer = setTimeout(() => {
      api
        .get("/api/purchase-orders", {
          params: { q: term.trim(), perPage: 8 },
        })
        .then(({ data }) => active && setResults(data.purchaseOrders ?? []))
        .catch(() => active && setResults([]));
    }, 250);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [term]);

  const rows =
    results ??
    (suggested ?? []).map((entry) => ({
      id: entry.purchaseOrderId,
      poNumber: entry.poNumber,
      status: entry.status,
      total: entry.total,
      currency: entry.currency,
      supplierName: entry.supplierName,
    }));

  return (
    <div className="mt-3 rounded-lg border border-white/10 bg-ink-950/50 p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-slate-300">
          {results ? "Search results" : "Suggested orders"}
        </span>
        <button
          type="button"
          onClick={onClose}
          className="text-slate-500 transition-colors hover:text-slate-300"
          aria-label="Close"
        >
          <X size={13} />
        </button>
      </div>

      <input
        value={term}
        onChange={(event) => setTerm(event.target.value)}
        placeholder="Search by PO number or reference…"
        className="mt-2 w-full rounded-md border border-white/10 bg-ink-950/60 px-2.5 py-1.5 text-xs text-white placeholder:text-slate-500 focus:border-brand-400/50 focus:outline-none"
      />

      {error && <p className="mt-2 text-xs text-rose-300">{error}</p>}

      {suggested === null && !results ? (
        <div className="mt-3 flex items-center gap-2 text-xs text-slate-500">
          <Loader2 size={12} className="animate-spin" /> Looking…
        </div>
      ) : rows.length === 0 ? (
        <p className="mt-3 text-xs text-slate-500">
          {term.trim()
            ? "No orders match that."
            : "Nothing on this invoice points at an order. Search for it above."}
        </p>
      ) : (
        <ul className="mt-2 space-y-1">
          {rows.map((row) => (
            <li key={row.id}>
              <button
                type="button"
                disabled={busy}
                onClick={() => onPick(row.id)}
                className="flex w-full flex-wrap items-center justify-between gap-2 rounded-md border border-white/10 px-2.5 py-1.5 text-left text-xs transition-colors hover:bg-white/5 disabled:opacity-50"
              >
                <span className="font-medium text-white">{row.poNumber}</span>
                <span className="flex items-center gap-2 text-slate-400">
                  {row.supplierName && (
                    <span className="max-w-[12rem] truncate">{row.supplierName}</span>
                  )}
                  <span>{poStatusLabel(row.status)}</span>
                  <span className="tabular-nums">
                    {formatMoney(row.total, row.currency)}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Accepting discrepancies. The reason is required, by the server too. */
function AcceptForm({ busy, onSubmit, onCancel }) {
  const [note, setNote] = useState("");
  return (
    <form
      className="mt-3 rounded-lg border border-amber-400/25 bg-amber-500/[0.06] p-3"
      onSubmit={(event) => {
        event.preventDefault();
        if (note.trim()) onSubmit(note.trim());
      }}
    >
      <label className="block text-xs font-medium text-amber-100">
        Why are these acceptable?
      </label>
      <p className="mt-0.5 text-xs text-amber-200/70">
        Recorded against your name. The findings stay on the invoice either way.
      </p>
      <textarea
        value={note}
        onChange={(event) => setNote(event.target.value)}
        rows={2}
        maxLength={500}
        placeholder="e.g. Price rise agreed with the supplier by phone on 18 Nov."
        className="mt-2 w-full rounded-md border border-white/10 bg-ink-950/60 px-2.5 py-1.5 text-xs text-white placeholder:text-slate-500 focus:border-amber-400/50 focus:outline-none"
      />
      <div className="mt-2 flex gap-2">
        <button
          type="submit"
          disabled={busy || !note.trim()}
          className="inline-flex items-center gap-1.5 rounded-md border border-amber-400/40 bg-amber-500/20 px-2.5 py-1 text-xs font-medium text-amber-100 transition-colors hover:bg-amber-500/30 disabled:opacity-50"
        >
          {busy && <Loader2 size={12} className="animate-spin" />}
          Accept and record
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md border border-white/15 px-2.5 py-1 text-xs font-medium text-slate-300 transition-colors hover:bg-white/5"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
