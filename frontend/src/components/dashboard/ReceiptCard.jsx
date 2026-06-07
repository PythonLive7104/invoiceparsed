import { useState } from "react";
import {
  Store,
  Calendar,
  Hash,
  CreditCard,
  Tag,
  Coins,
  Receipt as ReceiptIcon,
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

/** Read-only result card for extracted receipts. */
export function ReceiptCard({ invoice: receipt, extractionId, fileName, initialShowDoc = false }) {
  const [showJson, setShowJson] = useState(false);
  const [showDoc, setShowDoc] = useState(initialShowDoc);
  const [copied, setCopied] = useState(false);

  const currency = receipt.currency || "USD";
  const conf = receipt.confidence || {};
  const scores = Object.values(conf).filter((v) => typeof v === "number");
  const overall = scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : null;

  function copyJson() {
    navigator.clipboard.writeText(JSON.stringify(receipt, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  }
  function downloadJson() {
    const blob = new Blob([JSON.stringify(receipt, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${receipt.merchant?.name || "receipt"}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }
  function downloadCsv() {
    if (!extractionId) return;
    downloadFile(`/api/extractions/${extractionId}/csv`, `${receipt.merchant?.name || "receipt"}.csv`);
  }

  return (
    <div className="glass overflow-hidden rounded-2xl">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.06] px-5 py-4 sm:px-6">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-brand-500/15 text-brand-300 ring-1 ring-inset ring-brand-400/20">
            <ReceiptIcon size={17} />
          </span>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-white">
              {receipt.merchant?.name || "Extracted receipt"}
            </div>
            {fileName && <div className="truncate text-xs text-slate-500">{fileName}</div>}
          </div>
          <span className="rounded-full bg-white/[0.06] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
            Receipt
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
            <Button size="sm" onClick={downloadCsv}>
              <Download size={14} /> CSV
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
        <pre className="max-h-[520px] overflow-auto bg-ink-950/60 p-5 font-mono text-[12.5px] leading-relaxed text-slate-300">
          {JSON.stringify(receipt, null, 2)}
        </pre>
      ) : (
        <div className="p-5 sm:p-6">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <Field icon={<Store size={15} />} label="Merchant" value={receipt.merchant?.name} confidence={conf.merchant} />
            <Field icon={<Calendar size={15} />} label="Date" value={receipt.receipt_date} confidence={conf.receipt_date} />
            <Field icon={<Tag size={15} />} label="Category" value={receipt.category} confidence={conf.category} />
            <Field icon={<CreditCard size={15} />} label="Payment method" value={receipt.payment_method} confidence={conf.payment_method} />
            <Field icon={<Coins size={15} />} label="Currency" value={receipt.currency} confidence={conf.currency} />
            <Field icon={<Hash size={15} />} label="Receipt #" value={receipt.receipt_number} confidence={conf.receipt_number} />
          </div>

          {receipt.merchant?.address && (
            <div className="mt-3">
              <Field icon={<Store size={15} />} label="Merchant address" value={receipt.merchant.address} confidence={conf.merchant} />
            </div>
          )}

          {receipt.line_items?.length > 0 && (
            <div className="mt-6 overflow-hidden rounded-xl border border-white/[0.07]">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-white/[0.03] text-left text-xs uppercase tracking-wider text-slate-500">
                    <th className="px-4 py-2.5 font-medium">Description</th>
                    <th className="px-3 py-2.5 text-right font-medium">Qty</th>
                    <th className="px-3 py-2.5 text-right font-medium">Price</th>
                    <th className="px-4 py-2.5 text-right font-medium">Amount</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.05]">
                  {receipt.line_items.map((li, idx) => (
                    <tr key={idx} className="text-slate-200">
                      <td className="px-4 py-2.5">{li.description || "—"}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{li.quantity ?? "—"}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{formatMoney(li.unit_price, currency)}</td>
                      <td className="px-4 py-2.5 text-right font-medium tabular-nums">{formatMoney(li.amount, currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="mt-5 flex justify-end">
            <div className="w-full max-w-xs space-y-1.5">
              <TotalRow label="Subtotal" value={formatMoney(receipt.subtotal, currency)} confidence={conf.subtotal} />
              <TotalRow label="Tax" value={formatMoney(receipt.tax, currency)} confidence={conf.tax} />
              {receipt.tip != null && <TotalRow label="Tip" value={formatMoney(receipt.tip, currency)} confidence={conf.tip} />}
              <div className="flex items-center justify-between border-t border-white/10 pt-2.5">
                <span className="flex items-center gap-2 text-sm font-semibold text-white">
                  Total <ConfidenceDot score={conf.total} />
                </span>
                <span className="text-lg font-semibold text-white tabular-nums">{formatMoney(receipt.total, currency)}</span>
              </div>
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

function TotalRow({ label, value, confidence }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="flex items-center gap-2 text-slate-400">{label} <ConfidenceDot score={confidence} /></span>
      <span className="text-slate-200 tabular-nums">{value}</span>
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
