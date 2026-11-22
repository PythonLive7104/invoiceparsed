import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, Circle, X, ArrowRight, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Getting-started checklist.
 *
 * The steps come from the server, which derives them from real state on every
 * request — so this can go backwards. Delete your only document and "Process
 * your first document" unticks itself, because it is true again. A stored
 * wizard position would keep claiming it was done.
 *
 * Hides itself once the required steps are complete, rather than lingering as a
 * row of ticks nobody needs.
 */
export function SetupChecklist() {
  const [state, setState] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    api
      .get("/api/organizations/current")
      .then(({ data }) => active && setState(data.onboarding))
      .catch(() => active && setState(null));
    return () => {
      active = false;
    };
  }, []);

  async function dismiss() {
    setBusy(true);
    try {
      const { data } = await api.post("/api/organizations/current/onboarding/dismiss");
      setState(data.onboarding);
    } catch {
      /* non-fatal: it is only a panel */
    }
    setBusy(false);
  }

  if (!state || state.dismissed || state.complete) return null;

  const { steps, completed, total } = state;
  const percent = total ? Math.round((completed / total) * 100) : 0;

  return (
    <div className="glass relative overflow-hidden rounded-2xl p-5 sm:p-6">
      <button
        onClick={dismiss}
        disabled={busy}
        title="Hide this"
        className="absolute right-4 top-4 grid h-8 w-8 place-items-center rounded-lg text-slate-500 transition-colors hover:bg-white/[0.06] hover:text-white disabled:opacity-50"
      >
        <X size={15} />
      </button>

      <div className="flex items-center gap-2">
        <Sparkles size={16} className="text-brand-300" />
        <h2 className="text-sm font-semibold text-white">Get set up</h2>
        <span className="text-xs text-slate-500">
          {completed} of {total}
        </span>
      </div>

      <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-white/[0.06]">
        <div
          className="h-full rounded-full bg-gradient-to-r from-brand-500 to-indigo-400 transition-[width] duration-500"
          style={{ width: `${percent}%` }}
        />
      </div>

      <ul className="mt-4 space-y-2.5">
        {steps.map((step) => {
          const Icon = step.done ? CheckCircle2 : Circle;
          const body = (
            <div className="flex items-start gap-3">
              <Icon
                size={17}
                className={cn(
                  "mt-0.5 shrink-0",
                  step.done ? "text-emerald-400" : "text-slate-600",
                )}
              />
              <div className="min-w-0 flex-1">
                <div
                  className={cn(
                    "flex items-center gap-2 text-sm font-medium",
                    step.done ? "text-slate-500 line-through" : "text-white",
                  )}
                >
                  {step.title}
                  {step.optional && !step.done && (
                    <span className="rounded-full bg-white/[0.06] px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-500">
                      Optional
                    </span>
                  )}
                </div>
                {!step.done && (
                  <p className="mt-0.5 text-xs text-slate-400">{step.description}</p>
                )}
              </div>
              {!step.done && step.action && (
                <ArrowRight size={15} className="mt-0.5 shrink-0 text-slate-600" />
              )}
            </div>
          );

          // Only unfinished steps that lead somewhere are links. A tick that
          // looks clickable and does nothing is worse than plain text.
          return (
            <li key={step.key}>
              {!step.done && step.action ? (
                <Link
                  to={step.action}
                  className="-mx-2 block rounded-lg px-2 py-1.5 transition-colors hover:bg-white/[0.04]"
                >
                  {body}
                </Link>
              ) : (
                <div className="-mx-2 px-2 py-1.5">{body}</div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
