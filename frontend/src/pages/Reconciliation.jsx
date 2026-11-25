import { useCallback, useEffect, useRef, useState } from "react";
import {
  Check,
  ChevronLeft,
  ChevronRight,
  EyeOff,
  Landmark,
  Link2,
  Loader2,
  Search,
  Undo2,
  Upload,
  X,
} from "lucide-react";
import { api, apiError } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/lib/auth.jsx";
import { PERMISSIONS } from "@/lib/permissions";
import { cn, formatDate, formatMoney } from "@/lib/utils";
import {
  PAYABLES,
  PAYABLES_COPY,
  UpgradePanel,
} from "@/components/dashboard/UpgradePanel";

/**
 * Bank reconciliation: did the money we think we paid actually leave the
 * account, once, for the right amount?
 *
 * Opens on **unmatched**, because that is the work. A screen that opens on
 * everything reconciled is a screen that hides the three lines nobody has
 * explained.
 *
 * Nothing here decides a match. The engine's suggestion arrives with a method
 * and a score and waits for a person — a plausible guess nobody checked is not
 * evidence that money moved.
 */

const STATUS = {
  unmatched: { label: "Unmatched", tone: "amber" },
  matched: { label: "Reconciled", tone: "emerald" },
  ignored: { label: "Set aside", tone: "slate" },
};

const TONES = {
  slate: "border-white/10 bg-white/[0.05] text-slate-300",
  amber: "border-amber-500/30 bg-amber-500/10 text-amber-200",
  emerald: "border-emerald-500/30 bg-emerald-500/10 text-emerald-200",
};

const METHOD_LABEL = {
  reference: "Reference matched",
  amount_date: "Amount and date",
  amount: "Amount only",
  fuzzy: "Amount and description",
  manual: "Chosen by hand",
};

const FILTERS = [
  ["unmatched", "Unmatched"],
  ["matched", "Reconciled"],
  ["ignored", "Set aside"],
  ["", "All"],
];

export default function Reconciliation() {
  const { can, has } = useAuth();
  const locked = !has(PAYABLES);
  const canWrite = can(PERMISSIONS.reconciliation);

  const [status, setStatus] = useState("unmatched");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [notice, setNotice] = useState(null);

  const load = useCallback(() => {
    if (locked) return undefined;
    let active = true;
    setLoading(true);
    const params = new URLSearchParams({ page: String(page), perPage: "25" });
    if (status) params.set("status", status);
    if (query.trim()) params.set("q", query.trim());
    api
      .get(`/api/reconciliation/transactions?${params}`)
      .then(({ data: body }) => active && setData(body))
      .catch(() => active && setData({ transactions: [], total: 0 }))
      .finally(() => active && setLoading(false));
    api
      .get("/api/reconciliation/summary")
      .then(({ data: body }) => active && setSummary(body))
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [page, status, query, locked]);

  useEffect(() => {
    const timer = setTimeout(load, query ? 300 : 0);
    return () => clearTimeout(timer);
  }, [load, query]);

  if (locked)
    return <UpgradePanel {...PAYABLES_COPY.reconciliation} icon={Landmark} />;

  const rows = data?.transactions ?? [];
  const pages = data?.pages ?? 1;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-white">
            Reconciliation
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Check your bank statement against the payments you recorded.
          </p>
        </div>
        {canWrite && (
          <Button onClick={() => setImporting((v) => !v)}>
            <Upload size={16} /> Import a statement
          </Button>
        )}
      </div>

      {importing && (
        <ImportPanel
          onClose={() => setImporting(false)}
          onDone={(result) => {
            setImporting(false);
            setNotice(result);
            setStatus("unmatched");
            setPage(1);
            load();
          }}
        />
      )}

      {notice && (
        <div className="flex items-start justify-between gap-3 rounded-xl border border-emerald-500/25 bg-emerald-500/[0.07] px-4 py-3 text-sm text-emerald-100">
          <span>
            Imported {notice.imported} line
            {notice.imported === 1 ? "" : "s"}
            {notice.duplicates > 0 && (
              <>
                , skipped {notice.duplicates} already present
              </>
            )}
            {notice.suggested > 0 && (
              <> — {notice.suggested} matched a payment, waiting for you to
                confirm</>
            )}
            .
          </span>
          <button
            type="button"
            onClick={() => setNotice(null)}
            className="shrink-0 text-emerald-300/70 hover:text-emerald-200"
            aria-label="Dismiss"
          >
            <X size={15} />
          </button>
        </div>
      )}

      {summary && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Tile label="Unmatched" value={summary.byStatus?.unmatched ?? 0}
            tone={summary.byStatus?.unmatched > 0 ? "amber" : "muted"}
            hint="Bank lines with no payment"
            onClick={() => { setStatus("unmatched"); setPage(1); }} />
          <Tile label="Awaiting confirmation"
            value={summary.awaitingConfirmation ?? 0} tone="muted"
            hint="Suggested, not yet checked" />
          <Tile label="Payments not seen"
            value={summary.unreconciledPayments ?? 0}
            tone={summary.unreconciledPayments > 0 ? "amber" : "muted"}
            hint="Recorded, but not on a statement" />
          <Tile label="Reconciled" value={summary.byStatus?.matched ?? 0}
            tone="muted" hint={`of ${summary.total} line${summary.total === 1 ? "" : "s"}`} />
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-[240px] max-w-sm flex-1">
          <Search size={16}
            className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            value={query}
            onChange={(event) => { setQuery(event.target.value); setPage(1); }}
            placeholder="Search description or reference…"
            className="h-11 w-full rounded-xl border border-white/10 bg-ink-900/60 pl-10 pr-3.5 text-sm text-white placeholder:text-slate-600 outline-none focus:border-brand-400/60 focus:ring-2 focus:ring-brand-400/20"
          />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {FILTERS.map(([value, label]) => (
            <button
              key={value || "all"}
              onClick={() => { setStatus(value); setPage(1); }}
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
            <Landmark size={26} />
          </span>
          <h3 className="mt-5 text-lg font-semibold text-white">
            {status === "unmatched" ? "Nothing to reconcile" : "Nothing here"}
          </h3>
          <p className="mt-1.5 max-w-sm text-sm text-slate-400">
            {status === "unmatched"
              ? "Every bank line is either reconciled or set aside. Import a statement to check a new period."
              : "Try a different filter."}
          </p>
        </div>
      ) : (
        <div className={cn("space-y-3", loading && "opacity-60")}>
          {rows.map((row) => (
            <TransactionRow key={row.id} row={row} onChanged={load}
              canWrite={canWrite} />
          ))}

          {pages > 1 && (
            <div className="flex items-center justify-between px-1 text-xs text-slate-400">
              <span>
                Page {page} of {pages} · {data.total} line
                {data.total === 1 ? "" : "s"}
              </span>
              <div className="flex gap-1">
                <button disabled={page <= 1} onClick={() => setPage((v) => v - 1)}
                  className="grid h-7 w-7 place-items-center rounded-md border border-white/10 disabled:opacity-40"
                  aria-label="Previous page">
                  <ChevronLeft size={14} />
                </button>
                <button disabled={page >= pages} onClick={() => setPage((v) => v + 1)}
                  className="grid h-7 w-7 place-items-center rounded-md border border-white/10 disabled:opacity-40"
                  aria-label="Next page">
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
    amber: "border-amber-500/30 bg-amber-500/[0.07]",
    muted: "border-white/[0.06] bg-white/[0.02]",
  };
  const Element = onClick ? "button" : "div";
  return (
    <Element
      {...(onClick ? { type: "button", onClick } : {})}
      className={cn("rounded-2xl border p-4 text-left", tones[tone] ?? tones.muted,
        onClick && "transition-colors hover:bg-white/[0.05]")}
    >
      <div className="text-xs uppercase tracking-wider text-slate-500">{label}</div>
      <div className="mt-1.5 text-2xl font-semibold tabular-nums text-white">
        {value ?? 0}
      </div>
      <div className="mt-0.5 text-xs text-slate-500">{hint}</div>
    </Element>
  );
}

function TransactionRow({ row, onChanged, canWrite }) {
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [picking, setPicking] = useState(false);

  async function act(key, request) {
    setBusy(key);
    setError(null);
    try {
      await request();
      setPicking(false);
      onChanged?.();
    } catch (err) {
      setError(apiError(err, "That didn't work."));
    } finally {
      setBusy(null);
    }
  }

  const entry = STATUS[row.status] ?? { label: row.status, tone: "slate" };
  const match = row.match;

  return (
    <div className="glass rounded-2xl p-4 sm:p-5">
      <div className="flex flex-wrap items-start gap-x-4 gap-y-2">
        <div className="min-w-0 flex-1">
          <div className="text-sm text-white">{row.description || "—"}</div>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-500">
            {row.date && <span>{formatDate(row.date)}</span>}
            {row.reference && (
              <>
                <span>·</span>
                <span>{row.reference}</span>
              </>
            )}
          </div>
        </div>
        <div className="text-right">
          <div
            className={cn(
              "tabular-nums text-sm",
              row.debit ? "text-rose-200" : "text-emerald-200",
            )}
          >
            {row.debit
              ? `− ${formatMoney(row.debit, row.currency)}`
              : `+ ${formatMoney(row.credit, row.currency)}`}
          </div>
          {row.balance && (
            <div className="text-xs text-slate-500">
              bal {formatMoney(row.balance, row.currency)}
            </div>
          )}
        </div>
        <span
          className={cn(
            "inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium whitespace-nowrap",
            TONES[entry.tone],
          )}
        >
          {entry.label}
        </span>
      </div>

      {row.ignoreReason && (
        <p className="mt-2 text-xs italic text-slate-500">
          Set aside: {row.ignoreReason}
        </p>
      )}

      {match && (
        <div
          className={cn(
            "mt-3 rounded-xl border p-3",
            match.status === "confirmed"
              ? "border-emerald-500/25 bg-emerald-500/[0.06]"
              : "border-white/10 bg-white/[0.03]",
          )}
        >
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
            <span className="font-medium text-slate-200">
              {match.status === "confirmed" ? "Reconciled against" : "Looks like"}
            </span>
            {match.payment && (
              <span className="tabular-nums text-slate-300">
                {formatMoney(match.payment.amount, match.payment.currency)}
              </span>
            )}
            {match.payment?.paidOn && (
              <span className="text-slate-500">
                {formatDate(match.payment.paidOn)}
              </span>
            )}
            {match.payment?.reference && (
              <span className="text-slate-500">{match.payment.reference}</span>
            )}
            <span className="text-slate-500">
              · {METHOD_LABEL[match.method] ?? match.method}
            </span>
            {match.difference && match.difference !== "0.00" && (
              <span className="text-amber-300">
                · differs by {formatMoney(match.difference, row.currency)}
              </span>
            )}
          </div>
          {match.confirmedBy && (
            <p className="mt-1 text-xs text-slate-500">
              Confirmed by {match.confirmedBy}
            </p>
          )}
        </div>
      )}

      {error && <p className="mt-2 text-xs text-rose-300">{error}</p>}

      {picking && (
        <CandidatePicker
          txnId={row.id}
          busy={busy === "match"}
          onClose={() => setPicking(false)}
          onPick={(paymentId) =>
            act("match", () =>
              api.post(`/api/reconciliation/transactions/${row.id}/match`, {
                paymentId,
              }),
            )
          }
        />
      )}

      {canWrite && !picking && (
        <div className="mt-3 flex flex-wrap gap-2">
          {match && match.status === "suggested" && (
            <button
              type="button"
              disabled={busy === "confirm"}
              onClick={() =>
                act("confirm", () =>
                  api.post(`/api/reconciliation/matches/${match.id}/confirm`),
                )
              }
              className="inline-flex items-center gap-1.5 rounded-md border border-emerald-400/40 bg-emerald-500/15 px-3 py-1.5 text-xs font-medium text-emerald-200 transition-colors hover:bg-emerald-500/25 disabled:opacity-50"
            >
              {busy === "confirm" ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <Check size={12} />
              )}
              Confirm
            </button>
          )}
          {match && (
            <button
              type="button"
              disabled={busy === "unmatch"}
              onClick={() =>
                act("unmatch", () =>
                  api.delete(`/api/reconciliation/matches/${match.id}`),
                )
              }
              className="inline-flex items-center gap-1.5 rounded-md border border-white/15 px-3 py-1.5 text-xs font-medium text-slate-300 transition-colors hover:bg-white/5 disabled:opacity-50"
            >
              <Undo2 size={12} /> Unmatch
            </button>
          )}
          {row.status !== "matched" && (
            <button
              type="button"
              onClick={() => setPicking(true)}
              className="inline-flex items-center gap-1.5 rounded-md border border-white/15 px-3 py-1.5 text-xs font-medium text-slate-300 transition-colors hover:bg-white/5"
            >
              <Link2 size={12} /> {match ? "Choose another" : "Match by hand"}
            </button>
          )}
          {row.status === "unmatched" && (
            <button
              type="button"
              onClick={() => {
                const reason = window.prompt(
                  "Why does this line not need reconciling?\n"
                  + "e.g. bank charges, interest, transfer between our own accounts",
                );
                if (reason?.trim())
                  act("ignore", () =>
                    api.post(
                      `/api/reconciliation/transactions/${row.id}/ignore`,
                      { reason },
                    ),
                  );
              }}
              className="inline-flex items-center gap-1.5 rounded-md border border-white/15 px-3 py-1.5 text-xs font-medium text-slate-400 transition-colors hover:bg-white/5"
            >
              <EyeOff size={12} /> Set aside
            </button>
          )}
          {row.status === "ignored" && (
            <button
              type="button"
              disabled={busy === "unignore"}
              onClick={() =>
                act("unignore", () =>
                  api.post(
                    `/api/reconciliation/transactions/${row.id}/unignore`,
                  ),
                )
              }
              className="rounded-md border border-white/15 px-3 py-1.5 text-xs font-medium text-slate-300 transition-colors hover:bg-white/5 disabled:opacity-50"
            >
              Bring back
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function CandidatePicker({ txnId, busy, onPick, onClose }) {
  const [rows, setRows] = useState(null);

  useEffect(() => {
    let active = true;
    api
      .get(`/api/reconciliation/transactions/${txnId}/candidates`)
      .then(({ data }) => active && setRows(data.candidates ?? []))
      .catch(() => active && setRows([]));
    return () => {
      active = false;
    };
  }, [txnId]);

  return (
    <div className="mt-3 rounded-xl border border-white/10 bg-ink-950/50 p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-slate-300">
          Payments this could be
        </span>
        <button type="button" onClick={onClose}
          className="text-slate-500 transition-colors hover:text-slate-300"
          aria-label="Close">
          <X size={13} />
        </button>
      </div>

      {rows === null ? (
        <div className="mt-3 flex items-center gap-2 text-xs text-slate-500">
          <Loader2 size={12} className="animate-spin" /> Looking…
        </div>
      ) : rows.length === 0 ? (
        <p className="mt-3 text-xs text-slate-500">
          No recorded payment resembles this line. Record the payment on the
          payables page first, or set this line aside.
        </p>
      ) : (
        <ul className="mt-2 space-y-1">
          {rows.map((entry) => (
            <li key={entry.paymentId}>
              <button
                type="button"
                disabled={busy}
                onClick={() => onPick(entry.paymentId)}
                className="flex w-full flex-wrap items-center justify-between gap-2 rounded-md border border-white/10 px-2.5 py-1.5 text-left text-xs transition-colors hover:bg-white/5 disabled:opacity-50"
              >
                <span className="text-white">
                  {entry.invoiceNumber || entry.vendorName || "Payment"}
                </span>
                <span className="flex items-center gap-2 text-slate-400">
                  {entry.reference && <span>{entry.reference}</span>}
                  {entry.paidOn && <span>{formatDate(entry.paidOn)}</span>}
                  <span className="tabular-nums">
                    {formatMoney(entry.amount, entry.currency)}
                  </span>
                  <span className="text-slate-500">
                    {METHOD_LABEL[entry.method] ?? entry.method}
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

/** Import a statement: a file, or one the extractor has already read. */
function ImportPanel({ onClose, onDone }) {
  const fileRef = useRef(null);
  const [statements, setStatements] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;
    api
      .get("/api/extractions?docType=statement")
      .then(({ data }) =>
        active &&
        setStatements(
          (data.extractions ?? []).filter((row) => row.status === "completed"),
        ),
      )
      .catch(() => active && setStatements([]));
    return () => {
      active = false;
    };
  }, []);

  async function send(payload, isFile) {
    setBusy(true);
    setError(null);
    try {
      const { data } = isFile
        ? await api.post("/api/reconciliation/imports", payload)
        : await api.post("/api/reconciliation/imports", payload);
      onDone(data);
    } catch (err) {
      setError(apiError(err, "Couldn't import that statement."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="glass rounded-2xl p-5 sm:p-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-white">
            Import a statement
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            Importing the same statement twice is harmless — lines already here
            are counted and skipped.
          </p>
        </div>
        <button type="button" onClick={onClose}
          className="text-slate-500 transition-colors hover:text-slate-300"
          aria-label="Close">
          <X size={16} />
        </button>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <div className="rounded-xl border border-white/[0.07] p-4">
          <h3 className="text-sm font-medium text-white">From a file</h3>
          <p className="mt-0.5 text-xs text-slate-500">
            CSV or Excel. Needs a date column and either an amount, or separate
            debit and credit columns.
          </p>
          <input
            ref={fileRef}
            type="file"
            accept=".csv,.xlsx,.xls,.txt"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (!file) return;
              const payload = new FormData();
              payload.append("file", file);
              send(payload, true);
            }}
            className="mt-3 block w-full text-xs text-slate-400 file:mr-3 file:rounded-md file:border file:border-white/15 file:bg-white/[0.04] file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-slate-200 hover:file:bg-white/[0.08]"
          />
        </div>

        <div className="rounded-xl border border-white/[0.07] p-4">
          <h3 className="text-sm font-medium text-white">
            From a statement you already extracted
          </h3>
          <p className="mt-0.5 text-xs text-slate-500">
            Reuses what the extractor read, rather than parsing the PDF again.
          </p>
          {statements === null ? (
            <Loader2 className="mt-3 animate-spin text-brand-400" size={16} />
          ) : statements.length === 0 ? (
            <p className="mt-3 text-xs text-slate-500">
              No bank statements extracted yet. Upload one on the Extract page
              first.
            </p>
          ) : (
            <ul className="mt-3 space-y-1">
              {statements.slice(0, 8).map((row) => (
                <li key={row.id}>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => send({ extractionId: row.id }, false)}
                    className="flex w-full items-center justify-between gap-2 rounded-md border border-white/10 px-2.5 py-1.5 text-left text-xs transition-colors hover:bg-white/5 disabled:opacity-50"
                  >
                    <span className="truncate text-slate-200">
                      {row.fileName}
                    </span>
                    <span className="shrink-0 text-slate-500">
                      {formatDate(row.createdAt)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {busy && (
        <div className="mt-4 flex items-center gap-2 text-xs text-slate-400">
          <Loader2 size={13} className="animate-spin" /> Importing…
        </div>
      )}
      {error && <p className="mt-4 text-sm text-rose-300">{error}</p>}
    </div>
  );
}
