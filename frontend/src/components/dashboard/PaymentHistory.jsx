import { useCallback, useEffect, useState } from "react";
import { Receipt, RefreshCw, Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth.jsx";

function formatAmount(amount, currency) {
  if (amount == null) return "—";
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: (currency || "USD").toUpperCase(),
    }).format(amount);
  } catch {
    return `${amount} ${currency || ""}`.trim();
  }
}

function formatDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

const SUCCESS = /succ|active|paid|complete/i;

export function PaymentHistory() {
  const { refreshUsage } = useAuth();
  const [payments, setPayments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const { data } = await api.get("/api/billing/payments");
      setPayments(data.payments || []);
    } catch {
      setError(true);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // "Confirm payment" — reconcile against Paystack directly (catches missed
  // webhooks), then refresh the plan/usage in the app shell.
  async function refresh() {
    setLoading(true);
    setError(false);
    try {
      const { data } = await api.post("/api/billing/sync");
      setPayments(data.payments || []);
      await refreshUsage();
    } catch {
      setError(true);
    }
    setLoading(false);
  }

  return (
    <div className="glass rounded-2xl p-6">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Receipt size={18} className="text-brand-300" />
          <h3 className="text-base font-semibold text-white">Payment history</h3>
        </div>
        <Button variant="secondary" onClick={refresh} disabled={loading} className="gap-1.5">
          {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          Confirm payment
        </Button>
      </div>

      <p className="mt-1.5 text-sm text-slate-400">
        Charges confirmed by Paystack appear here. Just paid and don't see your plan?
        Click <span className="text-slate-300">Confirm payment</span> to refresh.
      </p>

      <div className="mt-5">
        {loading && payments.length === 0 ? (
          <div className="flex items-center gap-2 py-6 text-sm text-slate-400">
            <Loader2 size={15} className="animate-spin" /> Loading…
          </div>
        ) : error ? (
          <div className="flex items-center gap-2 py-6 text-sm text-rose-300">
            <AlertCircle size={15} /> Couldn't load payments. Try again.
          </div>
        ) : payments.length === 0 ? (
          <div className="rounded-xl border border-white/10 bg-white/[0.02] px-4 py-6 text-center text-sm text-slate-400">
            No payments yet. Upgrades you complete through checkout will show up here.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/10 text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="py-2 pr-4 font-medium">Date</th>
                  <th className="py-2 pr-4 font-medium">Plan</th>
                  <th className="py-2 pr-4 font-medium">Amount</th>
                  <th className="py-2 pr-4 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {payments.map((p) => {
                  const ok = SUCCESS.test(p.status || "");
                  return (
                    <tr key={p.id} className="border-b border-white/5 last:border-0">
                      <td className="py-3 pr-4 text-slate-300">{formatDate(p.createdAt)}</td>
                      <td className="py-3 pr-4 capitalize text-slate-300">{p.plan || "—"}</td>
                      <td className="py-3 pr-4 text-slate-200">{formatAmount(p.amount, p.currency)}</td>
                      <td className="py-3 pr-4">
                        <span
                          className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs ${
                            ok
                              ? "bg-emerald-500/15 text-emerald-300"
                              : "bg-amber-500/15 text-amber-300"
                          }`}
                        >
                          {ok ? <CheckCircle2 size={12} /> : <AlertCircle size={12} />}
                          {p.status || "unknown"}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
