import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CheckCircle2, XCircle, Loader2, Clock } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth.jsx";
import { PLANS } from "@/lib/plans";

// Paystack transaction statuses, from the server-side verify.
const FAILURE = new Set(["failed", "abandoned", "reversed", "cancelled"]);
const SUCCESS = new Set(["success", "succeeded"]);

// If verify can't confirm it (a pending charge, or Paystack unreachable), fall back
// to watching for the webhook to flip the plan before showing "processing".
const POLL_ATTEMPTS = 8;
const POLL_INTERVAL = 2000;

export default function CheckoutReturn() {
  const { user, refreshUsage } = useAuth();
  const [params] = useSearchParams();
  const intendedPlan = params.get("plan");
  // Paystack appends both on the callback; they hold the same value.
  const reference = params.get("reference") || params.get("trxref");

  // checking | success | failed | processing
  const [state, setState] = useState("checking");
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;

    let cancelled = false;
    const planActivated = (u) =>
      intendedPlan ? u?.plan === intendedPlan : u?.plan && u.plan !== "free";

    // Ask the server to verify the reference with Paystack. This is authoritative and
    // activates the plan on the spot, so we don't have to race the webhook.
    async function verify() {
      if (!reference) return null;
      try {
        const { data } = await api.post("/api/billing/verify", { reference });
        return data?.status ?? null;
      } catch {
        return null; // fall through to polling
      }
    }

    // Fallback: the webhook may still be in flight. Watch for the plan to flip.
    async function poll(attempt = 0) {
      if (cancelled) return;
      const refreshed = await refreshUsage();
      if (cancelled) return;
      if (planActivated(refreshed)) {
        setState("success");
        return;
      }
      if (attempt + 1 >= POLL_ATTEMPTS) {
        // The charge most likely went through (Paystack redirected us here) but
        // nothing has confirmed it yet — don't claim failure.
        setState("processing");
        return;
      }
      setTimeout(() => poll(attempt + 1), POLL_INTERVAL);
    }

    (async () => {
      const status = await verify();
      if (cancelled) return;
      if (status && FAILURE.has(status)) {
        setState("failed");
        return;
      }
      if (status && SUCCESS.has(status)) {
        await refreshUsage().catch(() => {});
        if (!cancelled) setState("success");
        return;
      }
      poll();
    })();

    return () => {
      cancelled = true;
    };
  }, [reference, intendedPlan, refreshUsage]);

  // The auth context may confirm the plan independently of our polling.
  useEffect(() => {
    if (state !== "checking") return;
    const activated = intendedPlan
      ? user?.plan === intendedPlan
      : user?.plan && user.plan !== "free";
    if (activated) setState("success");
  }, [user, state, intendedPlan]);

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
