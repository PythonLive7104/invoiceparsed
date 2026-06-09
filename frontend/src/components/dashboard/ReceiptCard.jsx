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
  Pencil,
  PlusCircle,
  Trash2,
  Save,
  X,
  Loader2,
  Image as ImageIcon,
  AlertCircle,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { cn, formatMoney } from "@/lib/utils";
import { api, apiError, downloadFile } from "@/lib/api";
import { DocumentViewer } from "@/components/dashboard/DocumentViewer";

/** Result card for extracted receipts, with inline editing (parity with InvoiceCard). */
export function ReceiptCard({ invoice: initial, extractionId, fileName, initialShowDoc = false, onUpdated }) {
  const [receipt, setReceipt] = useState(initial);
  const [saved, setSaved] = useState(initial);
  const [editing, setEditing] = useState(false);
  const [showJson, setShowJson] = useState(false);
  const [showDoc, setShowDoc] = useState(initialShowDoc);
  const [copied, setCopied] = useState(false);
  const [savingState, setSavingState] = useState("idle"); // idle|saving|saved|error
  const [saveErr, setSaveErr] = useState(null);

  const currency = receipt.currency || "USD";
  const conf = receipt.confidence || {};
  const scores = Object.values(conf).filter((v) => typeof v === "number");
  const overall = scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : null;

  async function saveEdits() {
    if (!extractionId) {
      setSaved(receipt);
      setEditing(false);
      return;
    }
    setSavingState("saving");
    setSaveErr(null);
    try {
      const { data } = await api.patch(`/api/extractions/${extractionId}`, { invoice: receipt });
      setReceipt(data.invoice);
      setSaved(data.invoice);
      setEditing(false);
      setSavingState("saved");
      setTimeout(() => setSavingState("idle"), 2000);
      onUpdated?.(data);
    } catch (err) {
      setSaveErr(apiError(err, "Couldn't save changes."));
      setSavingState("error");
    }
  }

  function cancelEdits() {
    setReceipt(saved);
    setEditing(false);
    setSaveErr(null);
    setSavingState("idle");
  }

  function set(field, value) {
    setReceipt((r) => ({ ...r, [field]: value }));
  }
  function setMerchant(field, value) {
    setReceipt((r) => ({ ...r, merchant: { ...r.merchant, [field]: value } }));
  }
  function updateLine(idx, patch) {
    setReceipt((r) => ({
      ...r,
      line_items: r.line_items.map((li, i) => (i === idx ? { ...li, ...patch } : li)),
    }));
  }
  function num(v) {
    return v === "" ? null : Number(v);
  }

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
  function downloadXlsx() {
    if (!extractionId) return;
    downloadFile(`/api/extractions/${extractionId}/xlsx`, `${receipt.merchant?.name || "receipt"}.xlsx`);
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
          {editing ? (
            <>
              <Button size="sm" onClick={saveEdits} disabled={savingState === "saving"}>
                {savingState === "saving" ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                Save changes
              </Button>
              <button
                onClick={cancelEdits}
                className="inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-xs font-medium text-slate-300 transition-colors hover:bg-white/[0.06]"
              >
                <X size={14} /> Cancel
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => setEditing(true)}
                className="inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-xs font-medium text-slate-300 transition-colors hover:bg-white/[0.06]"
              >
                <Pencil size={14} /> Edit
              </button>
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
            </>
          )}
        </div>
      </div>

      {savingState === "saved" && (
        <div className="flex items-center gap-2 border-b border-white/[0.06] bg-emerald-500/[0.07] px-5 py-2.5 text-xs text-emerald-300 sm:px-6">
          <Check size={14} /> Changes saved.
        </div>
      )}
      {saveErr && (
        <div className="flex items-center gap-2 border-b border-white/[0.06] bg-red-500/[0.08] px-5 py-2.5 text-xs text-red-300 sm:px-6">
          <AlertCircle size={14} /> {saveErr}
        </div>
      )}

      {showDoc && extractionId && (
        <div className="border-b border-white/[0.06] p-4 sm:p-5">
          <DocumentViewer extractionId={extractionId} />
        </div>
      )}

      {showJson ? (
        <pre className="max-h-[520px] overflow-auto whitespace-pre-wrap break-words bg-ink-950/60 p-5 font-mono text-[12.5px] leading-relaxed text-slate-300">
          {JSON.stringify(receipt, null, 2)}
        </pre>
      ) : (
        <div className="p-5 sm:p-6">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <Field icon={<Store size={15} />} label="Merchant" value={receipt.merchant?.name} editing={editing} confidence={conf.merchant} onChange={(v) => setMerchant("name", v)} />
            <Field icon={<Calendar size={15} />} label="Date" value={receipt.receipt_date} editing={editing} confidence={conf.receipt_date} onChange={(v) => set("receipt_date", v)} />
            <Field icon={<Tag size={15} />} label="Category" value={receipt.category} editing={editing} confidence={conf.category} onChange={(v) => set("category", v)} />
            <Field icon={<CreditCard size={15} />} label="Payment method" value={receipt.payment_method} editing={editing} confidence={conf.payment_method} onChange={(v) => set("payment_method", v)} />
            <Field icon={<Coins size={15} />} label="Currency" value={receipt.currency} editing={editing} confidence={conf.currency} onChange={(v) => set("currency", v)} />
            <Field icon={<Hash size={15} />} label="Receipt #" value={receipt.receipt_number} editing={editing} confidence={conf.receipt_number} onChange={(v) => set("receipt_number", v)} />
          </div>

          {(receipt.merchant?.address || editing) && (
            <div className="mt-3">
              <Field icon={<Store size={15} />} label="Merchant address" value={receipt.merchant?.address} editing={editing} confidence={conf.merchant} onChange={(v) => setMerchant("address", v)} />
            </div>
          )}

          {(receipt.line_items?.length > 0 || editing) && (
            <div className="mt-6">
              <div className="mb-2 flex items-center justify-between">
                <h4 className="flex items-center gap-2 text-sm font-semibold text-white">
                  Line items <ConfidenceDot score={conf.line_items} />
                </h4>
                {editing && (
                  <button
                    onClick={() =>
                      setReceipt((r) => ({
                        ...r,
                        line_items: [...(r.line_items || []), { description: "", quantity: null, unit_price: null, amount: null }],
                      }))
                    }
                    className="inline-flex items-center gap-1.5 text-xs font-medium text-brand-300 hover:text-brand-200"
                  >
                    <PlusCircle size={14} /> Add row
                  </button>
                )}
              </div>
              <div className="overflow-hidden rounded-xl border border-white/[0.07]">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-white/[0.03] text-left text-xs uppercase tracking-wider text-slate-500">
                      <th className="px-4 py-2.5 font-medium">Description</th>
                      <th className="px-3 py-2.5 text-right font-medium">Qty</th>
                      <th className="px-3 py-2.5 text-right font-medium">Price</th>
                      <th className="px-4 py-2.5 text-right font-medium">Amount</th>
                      {editing && <th className="w-10" />}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/[0.05]">
                    {(receipt.line_items || []).length === 0 && (
                      <tr>
                        <td colSpan={editing ? 5 : 4} className="px-4 py-6 text-center text-sm text-slate-500">
                          No line items detected.
                        </td>
                      </tr>
                    )}
                    {(receipt.line_items || []).map((li, idx) => (
                      <tr key={idx} className="text-slate-200">
                        <td className="px-4 py-2.5">
                          <CellInput editing={editing} value={li.description ?? ""} onChange={(v) => updateLine(idx, { description: v })} display={li.description || "—"} />
                        </td>
                        <td className="px-3 py-2.5 text-right tabular-nums">
                          <CellInput editing={editing} numeric align="right" value={li.quantity ?? ""} onChange={(v) => updateLine(idx, { quantity: num(v) })} display={li.quantity ?? "—"} />
                        </td>
                        <td className="px-3 py-2.5 text-right tabular-nums">
                          <CellInput editing={editing} numeric align="right" value={li.unit_price ?? ""} onChange={(v) => updateLine(idx, { unit_price: num(v) })} display={formatMoney(li.unit_price, currency)} />
                        </td>
                        <td className="px-4 py-2.5 text-right font-medium tabular-nums">
                          <CellInput editing={editing} numeric align="right" value={li.amount ?? ""} onChange={(v) => updateLine(idx, { amount: num(v) })} display={formatMoney(li.amount, currency)} />
                        </td>
                        {editing && (
                          <td className="px-2 text-center">
                            <button
                              onClick={() => setReceipt((r) => ({ ...r, line_items: r.line_items.filter((_, i) => i !== idx) }))}
                              className="text-slate-500 transition-colors hover:text-red-400"
                            >
                              <Trash2 size={14} />
                            </button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <div className="mt-5 flex justify-end">
            <div className="w-full max-w-xs space-y-1.5">
              <TotalRow label="Subtotal" field="subtotal" value={receipt.subtotal} editing={editing} currency={currency} confidence={conf.subtotal} onChange={(v) => set("subtotal", num(v))} />
              <TotalRow label="Tax" field="tax" value={receipt.tax} editing={editing} currency={currency} confidence={conf.tax} onChange={(v) => set("tax", num(v))} />
              <TotalRow label="Tip" field="tip" value={receipt.tip} editing={editing} currency={currency} confidence={conf.tip} onChange={(v) => set("tip", num(v))} hideWhenEmpty />
              <div className="flex items-center justify-between border-t border-white/10 pt-2.5">
                <span className="flex items-center gap-2 text-sm font-semibold text-white">
                  Total <ConfidenceDot score={conf.total} />
                </span>
                {editing ? (
                  <input
                    value={receipt.total ?? ""}
                    inputMode="decimal"
                    onChange={(e) => set("total", num(e.target.value))}
                    className="h-8 w-28 rounded-md border border-white/10 bg-ink-950/60 px-2 text-right text-sm text-white outline-none focus:border-brand-400/60"
                  />
                ) : (
                  <span className="text-lg font-semibold text-white tabular-nums">{formatMoney(receipt.total, currency)}</span>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ icon, label, value, editing, onChange, confidence }) {
  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-3.5 py-3">
      <div className="flex items-center justify-between gap-1.5 text-xs font-medium uppercase tracking-wider text-slate-500">
        <span className="flex items-center gap-1.5"><span className="text-slate-500">{icon}</span>{label}</span>
        <ConfidenceDot score={confidence} />
      </div>
      {editing ? (
        <input
          value={value ?? ""}
          onChange={(e) => onChange(e.target.value)}
          className="mt-1.5 h-8 w-full rounded-md border border-white/10 bg-ink-950/60 px-2 text-sm text-white outline-none focus:border-brand-400/60"
        />
      ) : (
        <div className="mt-1 truncate text-sm font-medium text-white">{value || "—"}</div>
      )}
    </div>
  );
}

function CellInput({ editing, value, onChange, display, numeric, align }) {
  if (!editing) return display;
  return (
    <input
      value={value}
      inputMode={numeric ? "decimal" : "text"}
      onChange={(e) => onChange(e.target.value)}
      className={cn(
        "h-8 w-full rounded-md border border-white/10 bg-ink-950/60 px-2 text-sm text-white outline-none focus:border-brand-400/60",
        align === "right" && "text-right",
      )}
    />
  );
}

function TotalRow({ label, value, editing, currency, confidence, onChange, hideWhenEmpty }) {
  if (!editing && hideWhenEmpty && value == null) return null;
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="flex items-center gap-2 text-slate-400">{label} <ConfidenceDot score={confidence} /></span>
      {editing ? (
        <input
          value={value ?? ""}
          inputMode="decimal"
          onChange={(e) => onChange(e.target.value)}
          className="h-8 w-28 rounded-md border border-white/10 bg-ink-950/60 px-2 text-right text-sm text-white outline-none focus:border-brand-400/60"
        />
      ) : (
        <span className="text-slate-200 tabular-nums">{formatMoney(value, currency)}</span>
      )}
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
