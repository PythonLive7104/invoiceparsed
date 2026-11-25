import { useCallback, useEffect, useState } from "react";
import { Loader2, PackageCheck, Plus, X } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/lib/auth.jsx";
import { PERMISSIONS } from "@/lib/permissions";
import { cn, formatDate } from "@/lib/utils";

/**
 * Deliveries against one purchase order.
 *
 * Three counts per line, because they have three different consequences:
 * what arrived, how much of it was broken, and how much went straight back.
 * What is left — accepted — is the only one an invoice is measured against,
 * and it is shown as a derived figure rather than typed, so the arithmetic
 * cannot disagree with the server's.
 *
 * A receipt is a draft until it is posted. Only a posted one moves the order
 * or satisfies an invoice, which is why posting is a separate button rather
 * than something that happens when you save.
 */

const STATUS_TONE = {
  draft: "border-white/10 bg-white/[0.05] text-slate-300",
  posted: "border-emerald-500/30 bg-emerald-500/10 text-emerald-200",
  cancelled: "border-rose-500/30 bg-rose-500/10 text-rose-200",
};

const STATUS_LABEL = { draft: "Draft", posted: "Posted", cancelled: "Cancelled" };

/** Trim a server decimal for display: "3.0000" reads as 3, "2.50" as 2.5. */
function qty(value, fallback = "0") {
  if (value === null || value === undefined || value === "") return fallback;
  const text = String(value);
  return text.includes(".") ? text.replace(/\.?0+$/, "") || "0" : text;
}

export function Deliveries({ po, onChanged }) {
  const { can } = useAuth();
  const canRead = can(PERMISSIONS.goodsReceiptsRead);
  const canWrite = can(PERMISSIONS.goodsReceiptsWrite);

  const [receipts, setReceipts] = useState(null);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [recording, setRecording] = useState(false);

  const load = useCallback(() => {
    if (!canRead) return undefined;
    let active = true;
    api
      .get(`/api/goods-receipts?poId=${po.id}&perPage=50`)
      .then(({ data }) => active && setReceipts(data.goodsReceipts ?? []))
      .catch(() => active && setReceipts([]));
    return () => {
      active = false;
    };
  }, [po.id, canRead]);

  useEffect(load, [load]);

  if (!canRead) return null;

  async function act(key, request) {
    setBusy(key);
    setError(null);
    try {
      await request();
      load();
      onChanged?.();
    } catch (err) {
      setError(apiError(err, "That didn't work."));
    } finally {
      setBusy(null);
    }
  }

  const receivable = ["approved", "sent", "partially_received", "fully_received"]
    .includes(po.status);

  return (
    <div className="glass rounded-2xl p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <PackageCheck size={17} className="text-slate-400" />
          <h2 className="text-base font-semibold text-white">Deliveries</h2>
        </div>
        {canWrite && receivable && !recording && (
          <Button variant="secondary" size="sm" onClick={() => setRecording(true)}>
            <Plus size={15} /> Record a delivery
          </Button>
        )}
      </div>

      {!receivable && (
        <p className="mt-2 text-xs text-slate-500">
          This order is {po.status.replace(/_/g, " ")}, so nothing can be
          received against it.
        </p>
      )}

      {error && <p className="mt-3 text-sm text-rose-300">{error}</p>}

      {recording && (
        <RecordDelivery
          po={po}
          onClose={() => setRecording(false)}
          onSaved={() => {
            setRecording(false);
            load();
            onChanged?.();
          }}
        />
      )}

      {receipts === null ? (
        <div className="mt-4 flex items-center gap-2 text-xs text-slate-500">
          <Loader2 size={13} className="animate-spin" /> Loading deliveries…
        </div>
      ) : receipts.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">
          Nothing has been recorded as received against this order yet.
        </p>
      ) : (
        <ul className="mt-4 divide-y divide-white/[0.05]">
          {receipts.map((grn) => (
            <li key={grn.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3">
              <span className="font-medium text-white">{grn.grnNumber}</span>
              <span
                className={cn(
                  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium",
                  STATUS_TONE[grn.status],
                )}
              >
                {STATUS_LABEL[grn.status] ?? grn.status}
              </span>
              {grn.receivedDate && (
                <span className="text-xs text-slate-500">
                  {formatDate(grn.receivedDate)}
                </span>
              )}
              {grn.deliveryNoteRef && (
                <span className="text-xs text-slate-500">
                  Note {grn.deliveryNoteRef}
                </span>
              )}
              <span className="text-xs text-slate-500">
                {grn.lineCount} line{grn.lineCount === 1 ? "" : "s"}
              </span>

              <span className="ml-auto flex gap-2">
                {canWrite && grn.status === "draft" && (
                  <button
                    type="button"
                    disabled={busy === grn.id}
                    onClick={() =>
                      act(grn.id, () =>
                        api.post(`/api/goods-receipts/${grn.id}/post`),
                      )
                    }
                    className="inline-flex items-center gap-1.5 rounded-md border border-emerald-400/40 bg-emerald-500/15 px-2.5 py-1 text-xs font-medium text-emerald-200 transition-colors hover:bg-emerald-500/25 disabled:opacity-50"
                  >
                    {busy === grn.id && (
                      <Loader2 size={12} className="animate-spin" />
                    )}
                    Post
                  </button>
                )}
                {canWrite && grn.status !== "cancelled" && (
                  <button
                    type="button"
                    disabled={busy === grn.id}
                    onClick={() =>
                      act(grn.id, () =>
                        api.post(`/api/goods-receipts/${grn.id}/cancel`),
                      )
                    }
                    className="rounded-md border border-white/15 px-2.5 py-1 text-xs font-medium text-slate-400 transition-colors hover:bg-white/5 disabled:opacity-50"
                  >
                    Cancel
                  </button>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}

      {receipts !== null && receipts.some((r) => r.status === "draft") && (
        <p className="mt-3 text-xs text-amber-200/80">
          A draft delivery counts for nothing until it is posted — an invoice
          against it will still be held.
        </p>
      )}
    </div>
  );
}

/**
 * The form. Pre-filled with what is still outstanding on each line, because
 * the common case is "the rest of it arrived" and retyping the quantities is
 * how transcription errors get in.
 */
function RecordDelivery({ po, onClose, onSaved }) {
  const [lines, setLines] = useState(null);
  const [header, setHeader] = useState({
    receivedDate: new Date().toISOString().slice(0, 10),
    deliveryNoteRef: "",
    carrier: "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [fields, setFields] = useState({});

  useEffect(() => {
    let active = true;
    api
      .get(`/api/goods-receipts/purchase-orders/${po.id}/outstanding`)
      .then(({ data }) => {
        if (!active) return;
        setLines(
          (data.lines ?? []).map((line) => ({
            ...line,
            received: qty(line.quantityOutstanding, "0"),
            damaged: "",
            rejected: "",
            notes: "",
          })),
        );
      })
      .catch((err) => active && setError(apiError(err, "Couldn't load the order.")));
    return () => {
      active = false;
    };
  }, [po.id]);

  function setLine(index, key, value) {
    setLines((current) =>
      current.map((line, i) => (i === index ? { ...line, [key]: value } : line)),
    );
  }

  async function save(event) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setFields({});
    try {
      await api.post("/api/goods-receipts", {
        purchaseOrderId: po.id,
        ...header,
        // Only lines where something actually arrived. Sending zero-rows would
        // make a receipt that records nothing and cannot be posted.
        lines: lines
          .filter((line) => Number(line.received) > 0)
          .map((line) => ({
            purchaseOrderLineId: line.purchaseOrderLineId,
            quantityReceived: line.received,
            quantityDamaged: line.damaged || "0",
            quantityRejected: line.rejected || "0",
            notes: line.notes || null,
          })),
      });
      onSaved();
    } catch (err) {
      setFields(err?.response?.data?.fields ?? {});
      setError(apiError(err, "Couldn't record that delivery."));
    } finally {
      setSaving(false);
    }
  }

  if (!lines) {
    return (
      <div className="mt-4 rounded-xl border border-white/10 bg-ink-950/40 p-4">
        {error ? (
          <p className="text-sm text-rose-300">{error}</p>
        ) : (
          <Loader2 size={16} className="animate-spin text-brand-400" />
        )}
      </div>
    );
  }

  const nothing = !lines.some((line) => Number(line.received) > 0);

  return (
    <form
      onSubmit={save}
      className="mt-4 rounded-xl border border-white/10 bg-ink-950/40 p-4"
    >
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-medium text-white">Record a delivery</h3>
        <button
          type="button"
          onClick={onClose}
          className="text-slate-500 transition-colors hover:text-slate-300"
          aria-label="Close"
        >
          <X size={15} />
        </button>
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <Input
          label="Received on"
          type="date"
          value={header.receivedDate}
          onChange={(value) => setHeader((h) => ({ ...h, receivedDate: value }))}
        />
        <Input
          label="Delivery note"
          placeholder="DN-1234"
          value={header.deliveryNoteRef}
          onChange={(value) => setHeader((h) => ({ ...h, deliveryNoteRef: value }))}
        />
        <Input
          label="Carrier"
          placeholder="Optional"
          value={header.carrier}
          onChange={(value) => setHeader((h) => ({ ...h, carrier: value }))}
        />
      </div>

      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead>
            <tr className="border-b border-white/[0.06] text-left text-xs uppercase tracking-wider text-slate-500">
              <th className="py-2 pr-3 font-medium">Item</th>
              <th className="px-2 py-2 text-right font-medium">Outstanding</th>
              <th className="px-2 py-2 text-right font-medium">Received</th>
              <th className="px-2 py-2 text-right font-medium">Damaged</th>
              <th className="px-2 py-2 text-right font-medium">Rejected</th>
              <th className="px-2 py-2 text-right font-medium">Accepted</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/[0.05]">
            {lines.map((line, index) => {
              // Derived, never typed. The server computes the same figure the
              // same way, and a box someone can disagree with it in would be
              // a second opinion about what is owed.
              const accepted = Math.max(
                0,
                (Number(line.received) || 0) -
                  (Number(line.damaged) || 0) -
                  (Number(line.rejected) || 0),
              );
              const bad = fields[`lines.${index}.quantityDamaged`]
                || fields[`lines.${index}.quantityReceived`];
              return (
                <tr key={line.purchaseOrderLineId}>
                  <td className="py-2 pr-3">
                    <div className="text-slate-200">{line.description}</div>
                    {line.sku && (
                      <div className="text-xs text-slate-500">{line.sku}</div>
                    )}
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums text-slate-500">
                    {qty(line.quantityOutstanding)}
                  </td>
                  <Cell
                    value={line.received}
                    onChange={(v) => setLine(index, "received", v)}
                  />
                  <Cell
                    value={line.damaged}
                    onChange={(v) => setLine(index, "damaged", v)}
                  />
                  <Cell
                    value={line.rejected}
                    onChange={(v) => setLine(index, "rejected", v)}
                  />
                  <td className="px-2 py-2 text-right tabular-nums text-white">
                    {accepted}
                    {bad && (
                      <div className="text-xs font-normal text-rose-300">{bad}</div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="mt-3 text-xs text-slate-500">
        Accepted is what an invoice will be checked against — damaged and
        rejected goods are delivered but not owed for.
      </p>

      {error && <p className="mt-2 text-sm text-rose-300">{error}</p>}
      {fields.lines && <p className="mt-2 text-sm text-rose-300">{fields.lines}</p>}

      <div className="mt-4 flex gap-2">
        <Button type="submit" size="sm" disabled={saving || nothing}>
          {saving && <Loader2 size={14} className="animate-spin" />}
          Save as draft
        </Button>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md border border-white/15 px-3 py-1.5 text-xs font-medium text-slate-300 transition-colors hover:bg-white/5"
        >
          Cancel
        </button>
      </div>
      <p className="mt-2 text-xs text-slate-500">
        Saved as a draft. Post it when you are satisfied it is right — only a
        posted delivery counts.
      </p>
    </form>
  );
}

function Input({ label, value, onChange, ...rest }) {
  return (
    <label className="block">
      <span className="text-xs text-slate-400">{label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 h-10 w-full rounded-lg border border-white/10 bg-ink-950/60 px-3 text-sm text-white placeholder:text-slate-600 outline-none focus:border-brand-400/60"
        {...rest}
      />
    </label>
  );
}

function Cell({ value, onChange }) {
  return (
    <td className="px-2 py-2">
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        inputMode="decimal"
        placeholder="0"
        className="h-9 w-20 rounded-lg border border-white/10 bg-ink-950/60 px-2 text-right text-sm tabular-nums text-white placeholder:text-slate-600 outline-none focus:border-brand-400/60"
      />
    </td>
  );
}
