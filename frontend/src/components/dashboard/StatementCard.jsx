import { useState } from "react";
import {
  Landmark,
  User as UserIcon,
  Hash,
  Coins,
  CalendarRange,
  Copy,
  Check,
  Download,
  Code2,
  Image as ImageIcon,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { cn, formatMoney } from "@/lib/utils";
import { downloadFile } from "@/lib/api";
import { DocumentViewer } from "@/components/dashboard/DocumentViewer";

/** Read-only result card for extracted bank statements. */
export function StatementCard({ invoice: stmt, extractionId, fileName, initialShowDoc = false }) {
  const [showJson, setShowJson] = useState(false);
  const [showDoc, setShowDoc] = useState(initialShowDoc);
  const [copied, setCopied] = useState(false);

  const currency = stmt.currency || "";
  const conf = stmt.confidence || {};
  const scores = Object.values(conf).filter((v) => typeof v === "number");
  const overall = scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : null;
  const txns = stmt.transactions || [];

  function copyJson() {
    navigator.clipboard.writeText(JSON.stringify(stmt, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  }
  function downloadJson() {
    const blob = new Blob([JSON.stringify(stmt, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${stmt.account_holder || "statement"}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }
  function downloadCsv() {
    if (!extractionId) return;
    downloadFile(`/api/extractions/${extractionId}/csv`, `${stmt.account_holder || "statement"}.csv`);
  }
  function downloadXlsx() {
    if (!extractionId) return;
    downloadFile(`/api/extractions/${extractionId}/xlsx`, `${stmt.account_holder || "statement"}.xlsx`);
  }

  const period = [stmt.period_start, stmt.period_end].filter(Boolean).join(" – ") || "—";

  return (
    <div className="glass overflow-hidden rounded-2xl">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.06] px-5 py-4 sm:px-6">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-brand-500/15 text-brand-300 ring-1 ring-inset ring-brand-400/20">
            <Landmark size={17} />
          </span>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-white">
              {stmt.account_holder || stmt.bank_name || "Bank statement"}
            </div>
            {fileName && <div className="truncate text-xs text-slate-500">{fileName}</div>}
          </div>
          <span className="rounded-full bg-white/[0.06] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
            Statement
          </span>
          {overall != null && <ConfidenceBadge score={overall} />}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {extractionId && (
            <button
              onClick={() => setShowDoc((s) => !s)}
              className={cn(
                "inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-xs font-medium transition-colors",
                showDoc ? "bg-brand-500/20 text-brand-100 ring-1 ring-inset ring-brand-400/30" : "text-slate-300 hover:bg-white/[0.06]",
              )}
            >
              <ImageIcon size={14} /> Original
            </button>
          )}
          <button onClick={() => setShowJson((s) => !s)} className="inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-xs font-medium text-slate-300 transition-colors hover:bg-white/[0.06]">
            <Code2 size={14} /> {showJson ? "Fields" : "JSON"}
          </button>
          <button onClick={copyJson} className="inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-xs font-medium text-slate-300 transition-colors hover:bg-white/[0.06]">
            {copied ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
            {copied ? "Copied" : "Copy"}
          </button>
          <Button size="sm" variant="secondary" onClick={downloadJson}>
            <Download size={14} /> JSON
          </Button>
          {extractionId && (
            <Button size="sm" variant="secondary" onClick={downloadCsv}>
              <Download size={14} /> CSV
            </Button>
          )}
          {extractionId && (
            <Button size="sm" onClick={downloadXlsx}>
              <Download size={14} /> Excel
            </Button>
          )}
        </div>
      </div>

      {showDoc && extractionId && (
        <div className="border-b border-white/[0.06] p-4 sm:p-5">
          <DocumentViewer extractionId={extractionId} />
        </div>
      )}

      {showJson ? (
        <pre className="max-h-[520px] overflow-auto whitespace-pre-wrap break-words bg-ink-950/60 p-5 font-mono text-[12.5px] leading-relaxed text-slate-300">
          {JSON.stringify(stmt, null, 2)}
        </pre>
      ) : (
        <div className="p-5 sm:p-6">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <Field icon={<UserIcon size={15} />} label="Account holder" value={stmt.account_holder} confidence={conf.account_holder} />
            <Field icon={<Hash size={15} />} label="Account number" value={stmt.account_number} confidence={conf.account_number} />
            <Field icon={<Landmark size={15} />} label="Bank" value={stmt.bank_name} confidence={conf.bank_name} />
            <Field icon={<CalendarRange size={15} />} label="Period" value={period} confidence={conf.period_start} />
            <Field icon={<Coins size={15} />} label="Currency" value={stmt.currency} confidence={conf.currency} />
          </div>

          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Opening" value={formatMoney(stmt.opening_balance, currency)} confidence={conf.opening_balance} />
            <Stat label="Closing" value={formatMoney(stmt.closing_balance, currency)} confidence={conf.closing_balance} />
            <Stat label="Total debit" value={formatMoney(stmt.total_debit, currency)} confidence={conf.total_debit} tone="text-red-300" />
            <Stat label="Total credit" value={formatMoney(stmt.total_credit, currency)} confidence={conf.total_credit} tone="text-emerald-300" />
          </div>

          <div className="mt-6">
            <div className="mb-2 flex items-center justify-between">
              <h4 className="flex items-center gap-2 text-sm font-semibold text-white">
                Transactions <span className="text-xs font-normal text-slate-500">({txns.length})</span>
                <ConfidenceDot score={conf.transactions} />
              </h4>
            </div>
            <div className="max-h-[480px] overflow-auto rounded-xl border border-white/[0.07]">
              <table className="w-full min-w-[640px] text-sm">
                <thead className="sticky top-0 bg-ink-900">
                  <tr className="text-left text-xs uppercase tracking-wider text-slate-500">
                    <th className="px-3 py-2.5 font-medium">Date</th>
                    <th className="px-3 py-2.5 font-medium">Description</th>
                    <th className="px-3 py-2.5 text-right font-medium">Debit</th>
                    <th className="px-3 py-2.5 text-right font-medium">Credit</th>
                    <th className="px-3 py-2.5 text-right font-medium">Balance</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.05]">
                  {txns.length === 0 && (
                    <tr><td colSpan={5} className="px-3 py-6 text-center text-sm text-slate-500">No transactions detected.</td></tr>
                  )}
                  {txns.map((t, i) => (
                    <tr key={i} className="text-slate-200">
                      <td className="whitespace-nowrap px-3 py-2 text-slate-400">{t.date || "—"}</td>
                      <td className="px-3 py-2">{t.description || "—"}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-red-300">{t.debit != null ? formatMoney(t.debit, currency) : ""}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-emerald-300">{t.credit != null ? formatMoney(t.credit, currency) : ""}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{t.balance != null ? formatMoney(t.balance, currency) : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ icon, label, value, confidence }) {
  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-3.5 py-3">
      <div className="flex items-center justify-between gap-1.5 text-xs font-medium uppercase tracking-wider text-slate-500">
        <span className="flex items-center gap-1.5"><span className="text-slate-500">{icon}</span>{label}</span>
        <ConfidenceDot score={confidence} />
      </div>
      <div className="mt-1 truncate text-sm font-medium text-white">{value || "—"}</div>
    </div>
  );
}

function Stat({ label, value, confidence, tone }) {
  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-3.5 py-3">
      <div className="flex items-center justify-between text-xs font-medium uppercase tracking-wider text-slate-500">
        {label}
        <ConfidenceDot score={confidence} />
      </div>
      <div className={cn("mt-1 text-sm font-semibold tabular-nums", tone || "text-white")}>{value}</div>
    </div>
  );
}

function confColor(score) {
  if (typeof score !== "number") return null;
  if (score >= 0.9) return { dot: "bg-emerald-400", text: "text-emerald-400" };
  if (score >= 0.7) return { dot: "bg-amber-400", text: "text-amber-400" };
  return { dot: "bg-red-400", text: "text-red-400" };
}
function ConfidenceDot({ score }) {
  const c = confColor(score);
  if (!c) return null;
  const pct = Math.round(score * 100);
  return (
    <span title={`Extraction confidence: ${pct}%`} className="inline-flex items-center gap-1">
      <span className={cn("h-1.5 w-1.5 rounded-full", c.dot)} />
      <span className={cn("text-[10px] font-semibold tabular-nums", c.text)}>{pct}%</span>
    </span>
  );
}
function ConfidenceBadge({ score }) {
  const c = confColor(score);
  if (!c) return null;
  return (
    <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-white/[0.05] px-2.5 py-1 text-[11px] font-medium text-slate-300">
      <span className={cn("h-1.5 w-1.5 rounded-full", c.dot)} />
      {Math.round(score * 100)}% confident
    </span>
  );
}
