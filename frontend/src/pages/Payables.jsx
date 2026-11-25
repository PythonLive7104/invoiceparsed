import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Plus,
  Search,
  Undo2,
  Wallet,
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
 * Payables: what is owed, what has been paid, and what is late.
 *
 * **InvoiceParsed records payments; it does not make them.** Every control
 * here writes down something that has already happened at the bank. That is a
 * deliberate product boundary, and the copy says so rather than leaving people
 * to wonder whether a button is about to move money.
 *
 * Opens on what is still open, because a ledger that opens on everything
 * settled is a ledger nobody reads.
 */

const STATE = {
  unpaid: { label: "Unpaid", tone: "slate" },
  partially_paid: { label: "Part paid", tone: "sky" },
  paid: { label: "Paid", tone: "emerald" },
  overdue: { label: "Overdue", tone: "rose" },
  disputed: { label: "Disputed", tone: "amber" },
};

const TONES = {
  slate: "border-white/10 bg-white/[0.05] text-slate-300",
  sky: "border-sky-500/30 bg-sky-500/10 text-sky-200",
  emerald: "border-emerald-500/30 bg-emerald-500/10 text-emerald-200",
  rose: "border-rose-500/30 bg-rose-500/10 text-rose-200",
  amber: "border-amber-500/30 bg-amber-500/10 text-amber-200",
};

const FILTERS = [
  ["open", "Outstanding"],
  ["overdue", "Overdue"],
  ["disputed", "Disputed"],
  ["paid", "Settled"],
  ["", "All"],
];

function StateBadge({ state }) {
  const entry = STATE[state] ?? { label: state ?? "—", tone: "slate" };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium whitespace-nowrap",
        TONES[entry.tone],
      )}
    >
      {entry.label}
    </span>
  );
}

export default function Payables() {
  const { can, has } = useAuth();
  const locked = !has(PAYABLES);
  const canWrite = can(PERMISSIONS.paymentsWrite);

  const [state, setState] = useState("open");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [openId, setOpenId] = useState(null);

  const load = useCallback(() => {
    if (locked) return undefined;
    let active = true;
    setLoading(true);
    const params = new URLSearchParams({ page: String(page), perPage: "25" });
    if (state) params.set("state", state);
    if (query.trim()) params.set("q", query.trim());
    api
      .get(`/api/payments?${params}`)
      .then(({ data: body }) => active && setData(body))
      .catch(() => active && setData({ items: [], total: 0 }))
      .finally(() => active && setLoading(false));
    api
      .get("/api/payments/summary")
      .then(({ data: body }) => active && setSummary(body))
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [page, state, query, locked]);

  useEffect(() => {
    const timer = setTimeout(load, query ? 300 : 0);
    return () => clearTimeout(timer);
  }, [load, query]);

  if (locked)
    return <UpgradePanel {...PAYABLES_COPY.payables} icon={Wallet} />;

  const rows = data?.items ?? [];
  const pages = data?.pages ?? 1;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-white">
          Payables
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          What you owe and what you have paid. InvoiceParsed records payments —
          it never makes them.
        </p>
      </div>

      {summary && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Tile
            label="Overdue"
            value={summary.byState?.overdue ?? 0}
            tone={summary.byState?.overdue > 0 ? "rose" : "muted"}
            hint="Past the due date"
            onClick={() => {
              setState("overdue");
              setPage(1);
            }}
          />
          <Tile
            label="Disputed"
            value={summary.byState?.disputed ?? 0}
            tone={summary.byState?.disputed > 0 ? "amber" : "muted"}
            hint="Being argued about"
            onClick={() => {
              setState("disputed");
              setPage(1);
            }}
          />
          <Tile
            label="Part paid"
            value={summary.byState?.partially_paid ?? 0}
            tone="muted"
            hint="Something still outstanding"
          />
          <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4">
            <div className="text-xs uppercase tracking-wider text-slate-500">
              Outstanding
            </div>
            {(summary.outstandingByCurrency ?? []).length === 0 ? (
              <div className="mt-1.5 text-sm text-slate-500">Nothing owed</div>
            ) : (
              <ul className="mt-1.5 space-y-0.5">
                {summary.outstandingByCurrency.map((row) => (
                  <li
                    key={row.currency}
                    className="text-lg font-semibold tabular-nums text-white"
                  >
                    {formatMoney(row.amount, row.currency)}
                  </li>
                ))}
              </ul>
            )}
            <div className="mt-0.5 text-xs text-slate-500">
              Totalled per currency
            </div>
          </div>
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
            <Wallet size={26} />
          </span>
          <h3 className="mt-5 text-lg font-semibold text-white">
            {state === "open" ? "Nothing outstanding" : "Nothing here"}
          </h3>
          <p className="mt-1.5 max-w-sm text-sm text-slate-400">
            {state === "open"
              ? "Every invoice is settled or has nothing left to pay."
              : "Try a different filter."}
          </p>
        </div>
      ) : (
        <div className={cn("space-y-3", loading && "opacity-60")}>
          {rows.map((row) => (
            <InvoiceRow
              key={row.extractionId}
              row={row}
              expanded={openId === row.extractionId}
              onToggle={() =>
                setOpenId(openId === row.extractionId ? null : row.extractionId)
              }
              onChanged={load}
              canWrite={canWrite}
            />
          ))}

          {pages > 1 && (
            <div className="flex items-center justify-between px-1 text-xs text-slate-400">
              <span>
                Page {page} of {pages} · {data.total} invoice
                {data.total === 1 ? "" : "s"}
              </span>
              <div className="flex gap-1">
                <button
                  disabled={page <= 1}
                  onClick={() => setPage((v) => v - 1)}
                  className="grid h-7 w-7 place-items-center rounded-md border border-white/10 disabled:opacity-40"
                  aria-label="Previous page"
                >
                  <ChevronLeft size={14} />
                </button>
                <button
                  disabled={page >= pages}
                  onClick={() => setPage((v) => v + 1)}
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

function InvoiceRow({ row, expanded, onToggle, onChanged, canWrite }) {
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [warning, setWarning] = useState(null);
  const [form, setForm] = useState(null); // pay | dispute

  const load = useCallback(() => {
    let active = true;
    api
      .get(`/api/payments/invoices/${row.extractionId}`)
      .then(({ data }) => active && setDetail(data))
      .catch(() => active && setError("Couldn't load this invoice."));
    return () => {
      active = false;
    };
  }, [row.extractionId]);

  useEffect(() => {
    if (expanded && detail === null) load();
  }, [expanded, detail, load]);

  async function act(key, request) {
    setBusy(key);
    setError(null);
    try {
      const { data } = await request();
      setDetail(data);
      setWarning(data.warning ?? null);
      setForm(null);
      onChanged?.();
    } catch (err) {
      setError(apiError(err, "That didn't work."));
    } finally {
      setBusy(null);
    }
  }

  const live = detail ?? row;

  return (
    <div className="glass overflow-hidden rounded-2xl">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full flex-wrap items-center gap-x-4 gap-y-2 px-5 py-4 text-left transition-colors hover:bg-white/[0.02]"
      >
        <div className="min-w-0 flex-1">
          <div className="font-medium text-white">
            {row.invoiceNumber || row.extractionId.slice(0, 8)}
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-500">
            <span>{row.supplierName || row.vendorName || "—"}</span>
            {row.dueDate && (
              <>
                <span>·</span>
                <span>due {formatDate(row.dueDate)}</span>
              </>
            )}
          </div>
        </div>
        <div className="text-right">
          <div className="tabular-nums text-sm text-slate-200">
            {formatMoney(row.outstanding, row.currency)}
          </div>
          <div className="text-xs text-slate-500">
            of {formatMoney(row.total, row.currency)}
          </div>
        </div>
        <StateBadge state={row.state} />
      </button>

      {expanded && (
        <div className="border-t border-white/[0.06] px-5 py-4">
          {detail === null ? (
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <Loader2 size={13} className="animate-spin" /> Loading…
            </div>
          ) : (
            <>
              {live.disputed && (
                <p className="mb-4 rounded-lg border border-amber-400/25 bg-amber-500/10 px-3 py-2 text-xs leading-relaxed text-amber-100">
                  <span className="font-medium">
                    Disputed by {live.disputedBy}
                  </span>
                  {live.disputeReason && <>: “{live.disputeReason}”</>}
                </p>
              )}
              {warning && (
                <p className="mb-4 flex items-start gap-2 rounded-lg border border-amber-400/25 bg-amber-500/10 px-3 py-2 text-xs leading-relaxed text-amber-100">
                  <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                  {warning}
                </p>
              )}

              <Link
                to={`/dashboard/extractions/${row.extractionId}`}
                className="mb-4 inline-block text-sm text-indigo-300 hover:text-indigo-200"
              >
                Open the invoice →
              </Link>

              {live.payments?.length > 0 ? (
                <ul className="divide-y divide-white/[0.05]">
                  {live.payments.map((payment) => (
                    <li
                      key={payment.id}
                      className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5 text-sm"
                    >
                      <span
                        className={cn(
                          "tabular-nums",
                          payment.void
                            ? "text-slate-600 line-through"
                            : "text-slate-200",
                        )}
                      >
                        {formatMoney(payment.amount, payment.currency)}
                      </span>
                      <span className="text-xs text-slate-500">
                        {payment.paidOn && formatDate(payment.paidOn)}
                      </span>
                      <span className="text-xs text-slate-500">
                        {payment.method?.replace(/_/g, " ")}
                      </span>
                      {payment.reference && (
                        <span className="text-xs text-slate-500">
                          {payment.reference}
                        </span>
                      )}
                      {payment.void ? (
                        <span className="text-xs text-rose-300">
                          voided by {payment.voidedBy}
                          {payment.voidReason && ` — ${payment.voidReason}`}
                        </span>
                      ) : (
                        canWrite && (
                          <button
                            type="button"
                            onClick={() => {
                              const reason = window.prompt(
                                "Why is this payment being voided?",
                              );
                              if (reason?.trim())
                                act(payment.id, () =>
                                  api.post(`/api/payments/${payment.id}/void`, {
                                    reason,
                                  }),
                                );
                            }}
                            className="ml-auto inline-flex items-center gap-1 text-xs text-slate-400 transition-colors hover:text-rose-300"
                          >
                            <Undo2 size={11} /> Void
                          </button>
                        )
                      )}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-slate-500">
                  Nothing recorded against this invoice yet.
                </p>
              )}

              {error && <p className="mt-3 text-sm text-rose-300">{error}</p>}

              {form === "pay" && (
                <PaymentForm
                  outstanding={live.outstanding}
                  currency={live.currency}
                  busy={busy === "pay"}
                  onCancel={() => setForm(null)}
                  onSubmit={(body) =>
                    act("pay", () =>
                      api.post(`/api/payments/invoices/${row.extractionId}`, body),
                    )
                  }
                />
              )}

              {canWrite && !form && (
                <div className="mt-4 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => setForm("pay")}
                    className="inline-flex items-center gap-1.5 rounded-md border border-emerald-400/40 bg-emerald-500/15 px-3 py-1.5 text-xs font-medium text-emerald-200 transition-colors hover:bg-emerald-500/25"
                  >
                    <Plus size={12} /> Record a payment
                  </button>
                  {live.disputed ? (
                    <button
                      type="button"
                      disabled={busy === "undispute"}
                      onClick={() =>
                        act("undispute", () =>
                          api.delete(
                            `/api/payments/invoices/${row.extractionId}/dispute`,
                          ),
                        )
                      }
                      className="rounded-md border border-white/15 px-3 py-1.5 text-xs font-medium text-slate-300 transition-colors hover:bg-white/5 disabled:opacity-50"
                    >
                      Clear dispute
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => {
                        const reason = window.prompt("What is disputed?");
                        if (reason?.trim())
                          act("dispute", () =>
                            api.post(
                              `/api/payments/invoices/${row.extractionId}/dispute`,
                              { reason },
                            ),
                          );
                      }}
                      className="rounded-md border border-amber-400/40 bg-amber-500/15 px-3 py-1.5 text-xs font-medium text-amber-100 transition-colors hover:bg-amber-500/25"
                    >
                      Dispute
                    </button>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

const METHODS = [
  ["bank_transfer", "Bank transfer"],
  ["card", "Card"],
  ["direct_debit", "Direct debit"],
  ["cheque", "Cheque"],
  ["cash", "Cash"],
  ["other", "Other"],
];

function PaymentForm({ outstanding, currency, busy, onSubmit, onCancel }) {
  const [form, setForm] = useState({
    amount: outstanding ?? "",
    paidOn: new Date().toISOString().slice(0, 10),
    method: "bank_transfer",
    reference: "",
  });

  function set(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  return (
    <form
      className="mt-4 rounded-xl border border-white/10 bg-ink-950/40 p-4"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(form);
      }}
    >
      <h4 className="text-sm font-medium text-white">
        Record a payment you have already made
      </h4>
      <p className="mt-0.5 text-xs text-slate-500">
        Pre-filled with what is outstanding ({formatMoney(outstanding, currency)}).
      </p>
      <div className="mt-3 grid gap-3 sm:grid-cols-4">
        <label className="block">
          <span className="text-xs text-slate-400">Amount</span>
          <input
            value={form.amount}
            onChange={(event) => set("amount", event.target.value)}
            inputMode="decimal"
            className="mt-1 h-10 w-full rounded-lg border border-white/10 bg-ink-950/60 px-3 text-sm tabular-nums text-white outline-none focus:border-brand-400/60"
          />
        </label>
        <label className="block">
          <span className="text-xs text-slate-400">Paid on</span>
          <input
            type="date"
            value={form.paidOn}
            max={new Date().toISOString().slice(0, 10)}
            onChange={(event) => set("paidOn", event.target.value)}
            className="mt-1 h-10 w-full rounded-lg border border-white/10 bg-ink-950/60 px-3 text-sm text-white outline-none focus:border-brand-400/60"
          />
        </label>
        <label className="block">
          <span className="text-xs text-slate-400">Method</span>
          <select
            value={form.method}
            onChange={(event) => set("method", event.target.value)}
            className="mt-1 h-10 w-full rounded-lg border border-white/10 bg-ink-950/60 px-3 text-sm text-white outline-none focus:border-brand-400/60"
          >
            {METHODS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="text-xs text-slate-400">Bank reference</span>
          <input
            value={form.reference}
            onChange={(event) => set("reference", event.target.value)}
            placeholder="FT-9001"
            className="mt-1 h-10 w-full rounded-lg border border-white/10 bg-ink-950/60 px-3 text-sm text-white placeholder:text-slate-600 outline-none focus:border-brand-400/60"
          />
        </label>
      </div>
      <p className="mt-2 text-xs text-slate-500">
        The reference is what reconciliation matches on, so it is worth getting
        right.
      </p>
      <div className="mt-3 flex gap-2">
        <Button type="submit" size="sm" disabled={busy || !form.amount}>
          {busy && <Loader2 size={13} className="animate-spin" />}
          Record payment
        </Button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md border border-white/15 px-3 py-1.5 text-xs font-medium text-slate-300 transition-colors hover:bg-white/5"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
