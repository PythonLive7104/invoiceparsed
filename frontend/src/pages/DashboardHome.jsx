import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, FileText } from "lucide-react";
import { ExtractWorkspace } from "@/components/dashboard/ExtractWorkspace";
import { UsageMeter } from "@/components/dashboard/UsageMeter";
import { UsageStats } from "@/components/dashboard/UsageStats";
import { SetupChecklist } from "@/components/dashboard/SetupChecklist";
import { WhatsNew } from "@/components/dashboard/WhatsNew";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth.jsx";
import { formatDate, formatMoney } from "@/lib/utils";

export default function DashboardHome() {
  const { user, usage } = useAuth();
  const [recent, setRecent] = useState([]);

  useEffect(() => {
    let active = true;
    api
      .get("/api/extractions")
      .then(({ data }) => {
        if (!active) return;
        setRecent(data.extractions.filter((e) => e.status === "completed").slice(0, 5));
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [usage?.used]);

  const firstName = user?.name?.split(" ")[0] || user?.email?.split("@")[0];

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-white sm:text-3xl">
          Welcome back, {firstName} 👋
        </h1>
        <p className="mt-1.5 text-slate-400">
          Drop an invoice, receipt or bank statement below and get clean, structured data in seconds.
        </p>
      </div>

      {/* Setup first while it is unfinished; it hides itself once the required
          steps are done, so it does not become permanent furniture. */}
      <SetupChecklist />

      {/* Below setup, above everything else. A brand-new account should finish
          getting started first; an existing customer sees no checklist, so for
          them this is the top of the page — which is the point, since they
          never revisit the landing page that announces anything. */}
      <WhatsNew />

      {/* Full width above the fold: these are the numbers that tell you
          whether anything needs doing today. */}
      <UsageStats />

      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        {/* The setup checklist links here by fragment, so this id is part of
            a contract with onboarding_state() in organization_routes.py. */}
        <div id="extract" className="min-w-0 scroll-mt-6">
          <ExtractWorkspace />
        </div>

        <aside className="min-w-0 space-y-4">
          <UsageMeter usage={usage} />

          <div className="glass rounded-2xl p-5">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-white">Recent</h3>
              <Link
                to="/dashboard/history"
                className="inline-flex items-center gap-1 text-xs font-medium text-brand-300 hover:text-brand-200"
              >
                View all <ArrowRight size={13} />
              </Link>
            </div>

            <div className="mt-4 space-y-1">
              {recent.length === 0 ? (
                <p className="py-4 text-center text-sm text-slate-500">No documents yet.</p>
              ) : (
                recent.map((r) => (
                  <Link
                    key={r.id}
                    to={`/dashboard/extractions/${r.id}`}
                    className="flex items-center gap-3 rounded-lg px-2 py-2 transition-colors hover:bg-white/[0.04]"
                  >
                    <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-brand-500/12 text-brand-300">
                      <FileText size={15} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium text-white">
                        {r.vendorName || r.invoiceNumber || "Invoice"}
                      </div>
                      <div className="truncate text-xs text-slate-500">{formatDate(r.createdAt)}</div>
                    </div>
                    <span className="shrink-0 text-sm font-medium text-slate-300 tabular-nums">
                      {formatMoney(r.total, r.currency)}
                    </span>
                  </Link>
                ))
              )}
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
