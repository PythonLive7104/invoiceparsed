import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CheckCircle2, XCircle, Loader2, Clock } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/lib/auth.jsx";
import { PLANS } from "@/lib/plans";

// Dodo appends a `status` query param on redirect. Map the values we know.
const FAILURE = new Set(["failed", "cancelled", "canceled", "declined", "expired"]);
const SUCCESS = new Set(["active", "succeeded", "paid", "completed", "complete", "success"]);

// How long to wait for the webhook to flip the plan before showing "processing".
const POLL_ATTEMPTS = 8;
const POLL_INTERVAL = 2000;

export default function CheckoutReturn() {
  const { user, refreshUsage } = useAuth();
  const [params] = useSearchParams();
  const intendedPlan = params.get("plan");
  const dodoStatus = (params.get("status") || "").toLowerCase();

  // checking | success | failed | processing
  const [state, setState] = useState(FAILURE.has(dodoStatus) ? "failed" : "checking");
  const startedRef = useRef(false);

  useEffect(() => {
    if (state !== "checking" || startedRef.current) return;
    startedRef.current = true;

    let attempts = 0;
    let cancelled = false;

    const planActivated = (u) =>
      intendedPlan ? u?.plan === intendedPlan : u?.plan && u.plan !== "free";

    async function poll() {
      if (cancelled) return;
      await refreshUsage();
      attempts += 1;
      // refreshUsage updates context async; re-read via the effect dependency on `user`.
      if (attempts >= POLL_ATTEMPTS) {
        // Payment likely went through (Dodo redirected us here) but the webhook
        // hasn't landed yet — don't claim failure.
        if (!cancelled) setState((s) => (s === "checking" ? "processing" : s));
        return;
      }
      setTimeout(poll, POLL_INTERVAL);
    }
    poll();

    return () => {
      cancelled = true;
    };
  }, [state, intendedPlan, refreshUsage]);

  // Whenever the user (plan) updates, check if activation completed.
  useEffect(() => {
    if (state !== "checking") return;
    const activated = intendedPlan ? user?.plan === intendedPlan : user?.plan && user.plan !== "free";
    if (activated || SUCCESS.has(dodoStatus)) {
      // If Dodo says success but the plan hasn't flipped yet, still prefer the
      // confirmed plan; treat as success once either signals it.
      if (activated) setState("success");
    }
  }, [user, state, intendedPlan, dodoStatus]);

  const planName = PLANS[intendedPlan]?.name || (intendedPlan ?? "your");

  return (
    <div className="mx-auto flex max-w-lg flex-col items-center px-4 py-16 text-center">
      {state === "checking" && (
        <>
          <Loader2 size={44} className="animate-spin text-brand-400" />
          <h1 className="mt-6 text-2xl font-semibold text-white">Confirming your payment…</h1>
          <p className="mt-2 text-slate-400">
            Hang tight — we're activating your {planName} plan. This usually takes a few seconds.
          </p>
        </>
      )}

      {state === "success" && (
        <>
          <CheckCircle2 size={48} className="text-emerald-400" />
          <h1 className="mt-6 text-2xl font-semibold text-white">Payment successful 🎉</h1>
          <p className="mt-2 text-slate-400">
            Your <span className="font-semibold capitalize text-slate-200">{planName}</span> plan is
            now active. Its features are unlocked across your account.
          </p>
          <Button to="/dashboard/billing" className="mt-8">
            Continue to billing
          </Button>
        </>
      )}

      {state === "processing" && (
        <>
          <Clock size={48} className="text-amber-400" />
          <h1 className="mt-6 text-2xl font-semibold text-white">Payment received</h1>
          <p className="mt-2 text-slate-400">
            Thanks! Your payment went through and your {planName} plan is being activated. It can
            take a moment to reflect — refresh the billing page shortly if it hasn't updated.
          </p>
          <Button to="/dashboard/billing" className="mt-8">
            Go to billing
          </Button>
        </>
      )}

      {state === "failed" && (
        <>
          <XCircle size={48} className="text-rose-400" />
          <h1 className="mt-6 text-2xl font-semibold text-white">Payment not completed</h1>
          <p className="mt-2 text-slate-400">
            Your payment was declined or cancelled, so no plan change was made and you weren't
            charged. You can try again or pick a different plan.
          </p>
          <div className="mt-8 flex gap-3">
            <Button to="/dashboard/billing">Back to plans</Button>
          </div>
        </>
      )}
    </div>
  );
}
