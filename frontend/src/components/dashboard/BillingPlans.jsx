import { useEffect, useState } from "react";
import { Check, Receipt, Loader2, BadgeCheck, Info } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";
import { PLAN_ORDER, PLANS } from "@/lib/plans";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth.jsx";

export function BillingPlans() {
  const { user, refreshUsage } = useAuth();
  const currentPlan = user?.plan;
  const [pending, setPending] = useState(null);
  const [live, setLive] = useState(false);

  useEffect(() => {
    api.get("/api/billing/config").then(({ data }) => setLive(!!data.live)).catch(() => {});
  }, []);

  async function choose(planId) {
    if (planId === currentPlan) return;
    setPending(planId);
    try {
      const { data } = await api.post("/api/billing/checkout", { plan: planId });
      if (data?.url) {
        // Live mode → hand off to the hosted Dodo Payments checkout.
        window.location.href = data.url;
        return;
      }
      await refreshUsage(); // demo mode applied instantly
    } catch {
      /* ignore */
    }
    setPending(null);
  }

  return (
    <div className="space-y-5">
      {!live && (
        <div className="flex items-start gap-2.5 rounded-xl border border-brand-400/20 bg-brand-500/[0.06] px-4 py-3 text-sm text-brand-200">
          <Info size={16} className="mt-0.5 shrink-0" />
          <span>
            Demo mode — plan changes apply instantly. In production this opens a secure Dodo
            Payments checkout.
          </span>
        </div>
      )}

      <div className="grid items-stretch gap-5 sm:grid-cols-2 xl:grid-cols-4">
        {PLAN_ORDER.map((id) => {
          const plan = PLANS[id];
          const isCurrent = id === currentPlan;
          return (
            <div
              key={id}
              className={cn(
                "relative flex h-full flex-col rounded-2xl p-7",
                plan.highlighted && !isCurrent ? "gradient-border bg-white/[0.04]" : "glass",
                isCurrent && "ring-1 ring-inset ring-emerald-400/40",
              )}
            >
              {isCurrent && (
                <span className="absolute -top-3 left-1/2 inline-flex -translate-x-1/2 items-center gap-1 rounded-full bg-emerald-500 px-3 py-1 text-xs font-semibold text-ink-950">
                  <BadgeCheck size={13} /> Current plan
                </span>
              )}
              {plan.highlighted && !isCurrent && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-brand-gradient px-3 py-1 text-xs font-semibold text-white shadow-glow-sm">
                  Most popular
                </span>
              )}

              <div className="flex items-center gap-2">
                <Receipt size={18} className="text-brand-300" />
                <h3 className="text-lg font-semibold text-white">{plan.name}</h3>
              </div>
              <div className="mt-4 flex items-end gap-1">
                <span className="text-4xl font-semibold tracking-tight text-white">${plan.price}</span>
                <span className="mb-1.5 text-sm text-slate-500">/mo</span>
              </div>
              <p className="mt-2 text-sm text-slate-400">{plan.tagline}</p>

              <ul className="mt-6 flex-1 space-y-3">
                {plan.features.map((f) => (
                  <li key={f} className="flex items-start gap-2.5 text-sm text-slate-300">
                    <Check size={17} className="mt-0.5 shrink-0 text-brand-400" />
                    {f}
                  </li>
                ))}
              </ul>

              <div className="mt-8">
                <Button
                  onClick={() => choose(id)}
                  disabled={isCurrent || pending !== null}
                  variant={plan.highlighted && !isCurrent ? "primary" : "secondary"}
                  className="w-full"
                >
                  {pending === id && <Loader2 size={15} className="animate-spin" />}
                  {isCurrent ? "Your plan" : plan.price === 0 ? "Switch to Free" : `Upgrade to ${plan.name}`}
                </Button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
