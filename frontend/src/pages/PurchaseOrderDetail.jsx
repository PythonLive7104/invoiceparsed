import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft, Loader2, Plus, Trash2, Save, FileDown, Paperclip, Send,
  CheckCircle2, XCircle, Ban, PackageCheck, Archive, X, ShieldAlert, Building2,
} from "lucide-react";
import { api, apiError, downloadFile } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { PoStatusBadge, poStatusLabel } from "@/components/dashboard/PoStatus";
import { MatchOutcomeBadge } from "@/components/dashboard/MatchStatus";
import { Deliveries } from "@/components/dashboard/Deliveries";
import { ApprovalChain } from "@/components/dashboard/ApprovalStatus";
import { cn, formatBytes, formatDate, formatMoney, numericInput } from "@/lib/utils";
import { useAuth } from "@/lib/auth.jsx";
import { PERMISSIONS } from "@/lib/permissions";

/**
 * One purchase order.
 *
 * Two things this page is careful about:
 *
 * 1. **Totals are never computed here.** Every figure shown comes from the
 *    server. A client-side total would be a second opinion about money, and
 *    the moment it disagreed with the stored one nobody could say which was
 *    right. The draft editor shows a live estimate, explicitly labelled as
 *    one, and the real figures replace it on save.
 * 2. **The lifecycle buttons come from the server's `nextStatuses`.** Keeping
 *    a copy of the state machine here would drift from the backend's, and the
 *    drift would show up as a button that 409s.
 */

const META_FIELDS = [
  ["orderDate", "Order date", "2026-11-23"],
  ["expectedDeliveryDate", "Expected delivery", "2026-12-15"],
  ["paymentTerms", "Payment terms", "Net 30"],
  ["reference", "Your reference", "REQ-2026-014"],
  ["department", "Department", "Operations"],
  ["costCenter", "Cost centre", "CC-120"],
  ["project", "Project", "Rig 4 refit"],
  ["category", "Category", "Consumables"],
];

const EMPTY_LINE = {
  description: "", sku: "", unit: "", quantity: "", unitPrice: "", taxRate: "",
};

export default function PurchaseOrderDetail() {
  const { id } = useParams();
  const { can } = useAuth();
  // Two separate capabilities: raising and amending an order, versus
  // authorizing it. A procurement officer has the first, an approver the
  // second, and the server enforces both again on every request - this only
  // keeps buttons from appearing that would answer 403.
  const canWrite = can(PERMISSIONS.purchaseOrdersWrite);
  const canApprove = can(PERMISSIONS.approvalsAct);
  const [po, setPo] = useState(null);
  const [approval, setApproval] = useState(null);
  const [error, setError] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [busy, setBusy] = useState(null);
  const [fieldErrors, setFieldErrors] = useState({});
  const [draft, setDraft] = useState(null);
  const [rejecting, setRejecting] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get(`/api/purchase-orders/${id}`);
      setPo(data.purchaseOrder);
      setApproval(data.approval ?? null);
    } catch {
      setNotFound(true);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  // The editable copy exists only while the order is a draft. Rebuilt whenever
  // the server's version changes so a save, a rejection or a status change
  // cannot leave stale values in the form.
  useEffect(() => {
    if (!po) return;
    if (!po.isEditable || !canWrite) {
      setDraft(null);
      return;
    }
    setDraft({
      currency: po.currency ?? "",
      poNumber: po.poNumber ?? "",
      deliveryAddress: po.deliveryAddress ?? "",
      notes: po.notes ?? "",
      ...Object.fromEntries(META_FIELDS.map(([key]) => [key, po[key] ?? ""])),
      lines: (po.lines ?? []).map((line) => ({
        description: line.description ?? "",
        sku: line.sku ?? "",
        unit: line.unit ?? "",
        // The server sends exact decimal strings ("3.0000"), which are correct
        // and unreadable in an input. Dropping trailing zeros is lossless, and
        // the value goes back as a string, so nothing passes through a float.
        quantity: trimDecimal(line.quantity),
        unitPrice: trimDecimal(line.unitPrice),
        taxRate: trimDecimal(line.taxRate),
      })),
    });
  }, [po, canWrite]);

  async function save() {
    setBusy("save");
    setError(null);
    setFieldErrors({});
    try {
      const { data } = await api.patch(`/api/purchase-orders/${id}`, {
        ...draft,
        lines: draft.lines.map((line) => ({
          description: line.description,
          sku: line.sku || null,
          unit: line.unit || null,
          quantity: line.quantity,
          unitPrice: line.unitPrice,
          taxRate: line.taxRate || "0",
        })),
      });
      setPo(data.purchaseOrder);
      setApproval(data.approval ?? null);
    } catch (err) {
      setFieldErrors(err?.response?.data?.fields ?? {});
      setError(apiError(err, "Couldn't save those changes."));
    } finally {
      setBusy(null);
    }
  }

  async function act(action, body) {
    setBusy(action);
    setError(null);
    try {
      const { data } = await api.post(`/api/purchase-orders/${id}/${action}`, body);
      setPo(data.purchaseOrder);
      setApproval(data.approval ?? null);
      setRejecting(false);
    } catch (err) {
      setError(apiError(err, "That didn't work."));
    } finally {
      setBusy(null);
    }
  }

  async function setStatus(status) {
    setBusy(status);
    setError(null);
    try {
      const { data } = await api.post(`/api/purchase-orders/${id}/status`, { status });
      setPo(data.purchaseOrder);
      setApproval(data.approval ?? null);
    } catch (err) {
      setError(apiError(err, "That didn't work."));
    } finally {
      setBusy(null);
    }
  }

  async function cancel() {
    setBusy("cancel");
    try {
      const { data } = await api.delete(`/api/purchase-orders/${id}`);
      setPo(data.purchaseOrder);
      setApproval(data.approval ?? null);
    } catch (err) {
      setError(apiError(err, "Couldn't cancel that order."));
    } finally {
      setBusy(null);
    }
  }

  async function downloadPdf() {
    setBusy("pdf");
    setError(null);
    try {
      await downloadFile(`/api/purchase-orders/${id}/pdf`, `${po.poNumber}.pdf`);
    } catch (err) {
      setError(apiError(err, "Couldn't generate that PDF."));
    } finally {
      setBusy(null);
    }
  }

  if (notFound) {
    return (
      <div className="glass rounded-2xl p-8 text-center">
        <h2 className="text-lg font-semibold text-white">Purchase order not found.</h2>
        <Link
          to="/dashboard/purchase-orders"
          className="mt-3 inline-block text-sm text-brand-300 hover:text-brand-200"
        >
          Back to purchase orders
        </Link>
      </div>
    );
  }
  if (!po) {
    return (
      <div className="grid place-items-center py-20">
        <Loader2 className="animate-spin text-brand-400" size={26} />
      </div>
    );
  }

  const next = po.nextStatuses ?? [];
  // The draft form only exists when the status permits editing AND this member
  // may write; `draft` is built under the same condition.
  const editing = Boolean(po.isEditable && canWrite && draft);

  return (
    <div className="space-y-6">
      <Link
        to="/dashboard/purchase-orders"
        className="inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-white"
      >
        <ArrowLeft size={16} /> All purchase orders
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight text-white">
              {po.poNumber}
            </h1>
            <PoStatusBadge status={po.status} />
          </div>
          {po.supplier && (
            <Link
              to={`/dashboard/suppliers/${po.supplier.id}`}
              className="mt-1.5 inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-white"
            >
              <Building2 size={14} /> {po.supplier.name}
            </Link>
          )}
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            onClick={downloadPdf}
            disabled={busy === "pdf"}
            className="inline-flex h-10 items-center gap-1.5 rounded-lg border border-white/10 px-3 text-sm text-slate-300 hover:bg-white/[0.06] hover:text-white disabled:opacity-50"
          >
            {busy === "pdf" ? (
              <Loader2 size={15} className="animate-spin" />
            ) : (
              <FileDown size={15} />
            )}
            PDF
          </button>

          {next.includes("pending_approval") && canWrite && (
            <Button onClick={() => act("submit")} disabled={busy === "submit"}>
              {busy === "submit" ? (
                <Loader2 size={15} className="animate-spin" />
              ) : (
                <Send size={15} />
              )}
              Submit for approval
            </Button>
          )}
          {po.status === "pending_approval" && canApprove && (
            <>
              <button
                onClick={() => setRejecting(true)}
                className="inline-flex h-10 items-center gap-1.5 rounded-lg border border-rose-500/30 px-3 text-sm text-rose-200 hover:bg-rose-500/10"
              >
                <XCircle size={15} /> Reject
              </button>
              <Button onClick={() => act("approve")} disabled={busy === "approve"}>
                {busy === "approve" ? (
                  <Loader2 size={15} className="animate-spin" />
                ) : (
                  <CheckCircle2 size={15} />
                )}
                Approve
              </Button>
            </>
          )}
          {next.includes("sent") && canWrite && (
            <Button onClick={() => setStatus("sent")} disabled={busy === "sent"}>
              <Send size={15} /> Mark sent
            </Button>
          )}
          {next.includes("partially_received") && canWrite && (
            <button
              onClick={() => setStatus("partially_received")}
              className="inline-flex h-10 items-center gap-1.5 rounded-lg border border-white/10 px-3 text-sm text-slate-300 hover:bg-white/[0.06] hover:text-white"
            >
              <PackageCheck size={15} /> Partly received
            </button>
          )}
          {next.includes("fully_received") && canWrite && (
            <Button
              onClick={() => setStatus("fully_received")}
              disabled={busy === "fully_received"}
            >
              <PackageCheck size={15} /> Received in full
            </Button>
          )}
          {next.includes("closed") && canWrite && (
            <button
              onClick={() => setStatus("closed")}
              className="inline-flex h-10 items-center gap-1.5 rounded-lg border border-white/10 px-3 text-sm text-slate-300 hover:bg-white/[0.06] hover:text-white"
            >
              <Archive size={15} /> Close
            </button>
          )}
          {next.includes("cancelled") && canWrite && (
            <button
              onClick={cancel}
              disabled={busy === "cancel"}
              title="Cancelled orders are kept — an invoice may still arrive against one"
              className="inline-flex h-10 items-center gap-1.5 rounded-lg px-3 text-sm text-slate-500 hover:bg-white/[0.06] hover:text-slate-300"
            >
              <Ban size={15} /> Cancel
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3.5 text-sm text-rose-200">
          {error}
        </div>
      )}

      {po.rejectionReason && po.status === "draft" && (
        <div className="flex items-start gap-3 rounded-xl border border-rose-500/25 bg-rose-500/[0.07] p-4">
          <XCircle size={17} className="mt-0.5 shrink-0 text-rose-400" />
          <div className="text-sm">
            <div className="font-semibold text-rose-200">Sent back for changes</div>
            <p className="mt-0.5 text-rose-100/80">{po.rejectionReason}</p>
          </div>
        </div>
      )}

      {po.isEditable && !canWrite && (
        <p className="flex items-start gap-2 text-xs text-slate-500">
          <ShieldAlert size={13} className="mt-0.5 shrink-0" />
          This order is still a draft, but your role does not include raising or
          amending purchase orders, so it is shown read-only.
        </p>
      )}

      {!po.isEditable && po.status !== "cancelled" && (
        <p className="flex items-start gap-2 text-xs text-slate-500">
          <ShieldAlert size={13} className="mt-0.5 shrink-0" />
          This order is {poStatusLabel(po.status).toLowerCase()} and its lines and
          prices are locked. Approval authorizes specific amounts; to change what
          was ordered, cancel it and raise a new order.
        </p>
      )}

      {/* ── Lines ─────────────────────────────────────────────────────────── */}
      {editing ? (
        <LineEditor
          draft={draft}
          setDraft={setDraft}
          currency={po.currency}
          fieldErrors={fieldErrors}
        />
      ) : (
        <ReadOnlyLines po={po} />
      )}

      {/* ── Details ───────────────────────────────────────────────────────── */}
      <div className="glass rounded-2xl p-5 sm:p-6">
        <h2 className="text-sm font-semibold text-white">Order details</h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {editing ? (
            <>
              {META_FIELDS.map(([key, label, placeholder]) => (
                <label key={key} className="block">
                  <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500">
                    {label}
                  </span>
                  <input
                    value={draft[key] ?? ""}
                    placeholder={placeholder}
                    onChange={(e) =>
                      setDraft((d) => ({ ...d, [key]: e.target.value }))
                    }
                    className="h-9 w-full rounded-lg border border-white/10 bg-ink-900/60 px-2.5 text-sm text-white placeholder:text-slate-600 outline-none focus:border-brand-400/60"
                  />
                  {fieldErrors[key] && (
                    <span className="mt-1 block text-xs text-rose-300">
                      {fieldErrors[key]}
                    </span>
                  )}
                </label>
              ))}
              <label className="block">
                <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500">
                  Currency
                </span>
                <input
                  value={draft.currency ?? ""}
                  maxLength={3}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, currency: e.target.value.toUpperCase() }))
                  }
                  className="h-9 w-full rounded-lg border border-white/10 bg-ink-900/60 px-2.5 text-sm uppercase text-white outline-none focus:border-brand-400/60"
                />
                {fieldErrors.currency && (
                  <span className="mt-1 block text-xs text-rose-300">
                    {fieldErrors.currency}
                  </span>
                )}
              </label>
              <label className="block">
                <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500">
                  PO number
                </span>
                <input
                  value={draft.poNumber ?? ""}
                  onChange={(e) => setDraft((d) => ({ ...d, poNumber: e.target.value }))}
                  className="h-9 w-full rounded-lg border border-white/10 bg-ink-900/60 px-2.5 text-sm text-white outline-none focus:border-brand-400/60"
                />
                {fieldErrors.poNumber && (
                  <span className="mt-1 block text-xs text-rose-300">
                    {fieldErrors.poNumber}
                  </span>
                )}
              </label>
            </>
          ) : (
            [
              ...META_FIELDS,
              ["currency", "Currency"],
            ].map(([key, label]) => (
              <div key={key}>
                <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
                  {label}
                </div>
                <div className="mt-1 text-sm text-slate-200">{po[key] || "—"}</div>
              </div>
            ))
          )}
        </div>

        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <div>
            <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
              Deliver to
            </div>
            {editing ? (
              <textarea
                rows={3}
                value={draft.deliveryAddress ?? ""}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, deliveryAddress: e.target.value }))
                }
                className="mt-1 w-full rounded-lg border border-white/10 bg-ink-900/60 p-2.5 text-sm text-white outline-none focus:border-brand-400/60"
              />
            ) : (
              <div className="mt-1 whitespace-pre-line text-sm text-slate-200">
                {po.deliveryAddress || "—"}
              </div>
            )}
          </div>
          <div>
            <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
              Notes
            </div>
            {editing ? (
              <textarea
                rows={3}
                value={draft.notes ?? ""}
                onChange={(e) => setDraft((d) => ({ ...d, notes: e.target.value }))}
                className="mt-1 w-full rounded-lg border border-white/10 bg-ink-900/60 p-2.5 text-sm text-white outline-none focus:border-brand-400/60"
              />
            ) : (
              <div className="mt-1 whitespace-pre-line text-sm text-slate-200">
                {po.notes || "—"}
              </div>
            )}
          </div>
        </div>

        {editing && (
          <div className="mt-5 flex justify-end">
            <Button onClick={save} disabled={busy === "save"}>
              {busy === "save" ? (
                <Loader2 size={15} className="animate-spin" />
              ) : (
                <Save size={15} />
              )}
              Save draft
            </Button>
          </div>
        )}
      </div>

      {/* Above the invoices, because the goods are the evidence those
          invoices are checked against, and reading downward follows the
          order of events: ordered, delivered, billed. */}
      {/* Above deliveries: whether this order is authorized at all comes
          before what arrived against it. */}
      {approval && (
        <div className="glass rounded-2xl p-5 sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <h2 className="text-base font-semibold text-white">Approval</h2>
              <span className="text-xs text-slate-500">{approval.ruleName}</span>
            </div>
            <Link
              to="/dashboard/approvals"
              className="text-sm text-indigo-300 hover:text-indigo-200"
            >
              Open approvals →
            </Link>
          </div>
          {approval.stuck && (
            <p className="mt-3 rounded-lg border border-rose-400/25 bg-rose-500/10 px-3 py-2 text-xs text-rose-100">
              Nobody is able to act on this — the approvers at this level have
              all left or no longer hold the role.
            </p>
          )}
          <ApprovalChain
            steps={approval.steps}
            currentLevel={approval.currentLevel}
            className="mt-4"
          />
        </div>
      )}

      <Deliveries po={po} onChanged={load} />

      <InvoicesAgainst poId={po.id} />

      <Attachments po={po} onChange={load} canWrite={canWrite} />

      <Trail po={po} />

      {rejecting && (
        <RejectDialog
          onClose={() => setRejecting(false)}
          onReject={(reason) => act("reject", { reason })}
          busy={busy === "reject"}
        />
      )}
    </div>
  );
}

/* ── Read-only lines ───────────────────────────────────────────────────────── */
function ReadOnlyLines({ po }) {
  return (
    <div className="glass overflow-hidden rounded-2xl">
      <h2 className="border-b border-white/[0.06] px-5 py-4 text-sm font-semibold text-white">
        Lines
      </h2>
      {po.lines.length === 0 ? (
        <p className="px-5 py-10 text-center text-sm text-slate-500">
          This order has no lines.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead>
              <tr className="border-b border-white/[0.06] text-left text-xs uppercase tracking-wider text-slate-500">
                <th className="px-5 py-3 font-medium">#</th>
                <th className="px-4 py-3 font-medium">Description</th>
                <th className="px-4 py-3 text-right font-medium">Qty</th>
                <th className="px-4 py-3 text-right font-medium">Unit price</th>
                <th className="px-4 py-3 text-right font-medium">Tax</th>
                <th className="px-4 py-3 text-right font-medium">Amount</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.05]">
              {po.lines.map((line) => (
                <tr key={line.id}>
                  <td className="px-5 py-3 text-slate-500">{line.lineNo}</td>
                  <td className="px-4 py-3">
                    <span className="text-slate-100">{line.description}</span>
                    {line.sku && (
                      <span className="block text-xs text-slate-500">SKU {line.sku}</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-slate-300">
                    {trimQty(line.quantity)}
                    {line.unit ? ` ${line.unit}` : ""}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-slate-300">
                    {formatMoney(line.unitPrice, po.currency)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-slate-400">
                    {trimQty(line.taxRate)}%
                  </td>
                  {/* The NET line amount. This column has to add up to the
                      Subtotal shown below it, or the table does not foot and
                      anyone checking the figures finds them disagreeing. */}
                  <td className="px-4 py-3 text-right tabular-nums text-white">
                    {formatMoney(line.lineSubtotal, po.currency)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Totals po={po} />
    </div>
  );
}

function Totals({ po }) {
  return (
    <div className="flex justify-end border-t border-white/[0.06] px-5 py-4">
      <dl className="w-full max-w-xs space-y-1.5 text-sm">
        <div className="flex justify-between">
          <dt className="text-slate-500">Subtotal</dt>
          <dd className="tabular-nums text-slate-200">
            {formatMoney(po.subtotal, po.currency)}
          </dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-slate-500">Tax</dt>
          <dd className="tabular-nums text-slate-200">
            {formatMoney(po.taxTotal, po.currency)}
          </dd>
        </div>
        <div className="flex justify-between border-t border-white/[0.08] pt-1.5 font-semibold">
          <dt className="text-white">Total</dt>
          <dd className="tabular-nums text-white">
            {formatMoney(po.total, po.currency)}
          </dd>
        </div>
      </dl>
    </div>
  );
}

/* ── Draft line editor ─────────────────────────────────────────────────────── */
function LineEditor({ draft, setDraft, currency, fieldErrors }) {
  // A live estimate, labelled as one. The server's figures are authoritative
  // and replace this on save; showing an unlabelled total computed in the
  // browser would be a second opinion about money.
  const estimate = useMemo(() => {
    let subtotal = 0;
    let tax = 0;
    for (const line of draft.lines) {
      const amount = Number(line.quantity || 0) * Number(line.unitPrice || 0);
      if (!Number.isFinite(amount)) continue;
      const rounded = Math.round(amount * 100) / 100;
      subtotal += rounded;
      tax += Math.round(rounded * Number(line.taxRate || 0)) / 100;
    }
    return { subtotal, tax, total: subtotal + tax };
  }, [draft.lines]);

  function setLine(index, patch) {
    setDraft((d) => ({
      ...d,
      lines: d.lines.map((line, i) => (i === index ? { ...line, ...patch } : line)),
    }));
  }

  return (
    <div className="glass overflow-hidden rounded-2xl">
      <div className="flex items-center justify-between border-b border-white/[0.06] px-5 py-4">
        <h2 className="text-sm font-semibold text-white">Lines</h2>
        <button
          onClick={() =>
            setDraft((d) => ({ ...d, lines: [...d.lines, { ...EMPTY_LINE }] }))
          }
          className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-white/10 px-3 text-sm text-slate-300 hover:bg-white/[0.06] hover:text-white"
        >
          <Plus size={15} /> Add line
        </button>
      </div>

      {draft.lines.length === 0 ? (
        <p className="px-5 py-10 text-center text-sm text-slate-500">
          No lines yet. Add one to describe what you are ordering.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[860px] text-sm">
            <thead>
              <tr className="border-b border-white/[0.06] text-left text-xs uppercase tracking-wider text-slate-500">
                <th className="px-5 py-3 font-medium">Description</th>
                <th className="px-3 py-3 font-medium">SKU</th>
                <th className="px-3 py-3 font-medium">Qty</th>
                <th className="px-3 py-3 font-medium">Unit</th>
                <th className="px-3 py-3 font-medium">Unit price</th>
                <th className="px-3 py-3 font-medium">Tax %</th>
                <th className="px-3 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.05]">
              {draft.lines.map((line, index) => (
                <tr key={index} className="align-top">
                  <td className="px-5 py-2.5">
                    <input
                      value={line.description}
                      placeholder="What are you buying?"
                      onChange={(e) => setLine(index, { description: e.target.value })}
                      className={cell(fieldErrors[`lines.${index}.description`])}
                    />
                    <FieldError message={fieldErrors[`lines.${index}.description`]} />
                  </td>
                  <td className="px-3 py-2.5">
                    <input
                      value={line.sku}
                      onChange={(e) => setLine(index, { sku: e.target.value })}
                      className={cn(cell(), "w-24")}
                    />
                  </td>
                  <td className="px-3 py-2.5">
                    <input
                      value={line.quantity ?? ""}
                      inputMode="decimal"
                      onChange={(e) =>
                        setLine(index, { quantity: numericInput(e.target.value) })
                      }
                      className={cn(
                        cell(fieldErrors[`lines.${index}.quantity`]),
                        "w-20 text-right tabular-nums",
                      )}
                    />
                    <FieldError message={fieldErrors[`lines.${index}.quantity`]} />
                  </td>
                  <td className="px-3 py-2.5">
                    <input
                      value={line.unit}
                      placeholder="each"
                      onChange={(e) => setLine(index, { unit: e.target.value })}
                      className={cn(cell(), "w-20")}
                    />
                  </td>
                  <td className="px-3 py-2.5">
                    <input
                      value={line.unitPrice ?? ""}
                      inputMode="decimal"
                      onChange={(e) =>
                        setLine(index, { unitPrice: numericInput(e.target.value) })
                      }
                      className={cn(
                        cell(fieldErrors[`lines.${index}.unitPrice`]),
                        "w-28 text-right tabular-nums",
                      )}
                    />
                    <FieldError message={fieldErrors[`lines.${index}.unitPrice`]} />
                  </td>
                  <td className="px-3 py-2.5">
                    <input
                      value={line.taxRate ?? ""}
                      inputMode="decimal"
                      placeholder="0"
                      onChange={(e) =>
                        setLine(index, { taxRate: numericInput(e.target.value) })
                      }
                      className={cn(
                        cell(fieldErrors[`lines.${index}.taxRate`]),
                        "w-20 text-right tabular-nums",
                      )}
                    />
                    <FieldError message={fieldErrors[`lines.${index}.taxRate`]} />
                  </td>
                  <td className="px-3 py-2.5">
                    <button
                      onClick={() =>
                        setDraft((d) => ({
                          ...d,
                          lines: d.lines.filter((_, i) => i !== index),
                        }))
                      }
                      title="Remove this line"
                      className="grid h-8 w-8 place-items-center rounded-lg text-slate-500 hover:bg-rose-500/10 hover:text-rose-300"
                    >
                      <Trash2 size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {draft.lines.length > 0 && (
        <div className="flex flex-wrap items-center justify-end gap-x-6 gap-y-1 border-t border-white/[0.06] px-5 py-4 text-sm">
          <span className="text-xs text-slate-500">
            Estimate — the saved order is calculated by the server
          </span>
          <span className="tabular-nums text-slate-400">
            Tax {formatMoney(estimate.tax.toFixed(2), currency)}
          </span>
          <span className="font-semibold tabular-nums text-white">
            {formatMoney(estimate.total.toFixed(2), currency)}
          </span>
        </div>
      )}
    </div>
  );
}

function cell(hasError) {
  return cn(
    "h-9 w-full min-w-[80px] rounded-lg border bg-ink-900/60 px-2.5 text-sm text-white placeholder:text-slate-600 outline-none focus:border-brand-400/60",
    hasError ? "border-rose-500/50" : "border-white/10",
  );
}

function FieldError({ message }) {
  if (!message) return null;
  return <span className="mt-1 block text-xs text-rose-300">{message}</span>;
}

/* ── Attachments ───────────────────────────────────────────────────────────── */
/**
 * What has actually been billed against this order.
 *
 * The figure that matters on a purchase order is not its total but what is
 * left on it, and that is only knowable from the invoices matched to it. Only
 * CONFIRMED invoices count toward "invoiced" — a suggestion nobody has
 * checked must not appear to consume an order's value, or the remaining figure
 * would be wrong in the direction that lets a genuine invoice look like
 * over-billing.
 */
function InvoicesAgainst({ poId }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    api
      .get(`/api/matching/purchase-orders/${poId}/invoices`)
      .then(({ data: body }) => active && setData(body))
      .catch(() => active && setError(true));
    return () => {
      active = false;
    };
  }, [poId]);

  if (error || !data) return null;

  return (
    <div className="glass rounded-2xl p-5 sm:p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-base font-semibold text-white">Invoices against this order</h2>
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-400">
          <span>
            Invoiced{" "}
            <span className="tabular-nums text-slate-200">
              {formatMoney(data.invoiced, data.currency)}
            </span>
          </span>
          <span>
            Remaining{" "}
            <span className="tabular-nums text-slate-200">
              {formatMoney(data.remaining, data.currency)}
            </span>
          </span>
        </div>
      </div>

      {data.items.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">
          Nothing has been billed against this order yet.
        </p>
      ) : (
        <ul className="mt-4 divide-y divide-white/[0.05]">
          {data.items.map((item) => (
            <li key={item.matchId} className="flex flex-wrap items-center gap-x-4 gap-y-1.5 py-2.5">
              <Link
                to={`/dashboard/extractions/${item.extractionId}`}
                className="min-w-0 flex-1 truncate text-sm font-medium text-white hover:text-brand-200"
              >
                {item.invoiceNumber || item.fileName}
              </Link>
              {item.invoiceDate && (
                <span className="text-xs text-slate-500">{formatDate(item.invoiceDate)}</span>
              )}
              <MatchOutcomeBadge outcome={item.outcome} overridden={item.overridden} />
              {item.status === "suggested" && (
                <span className="text-xs text-slate-500">not confirmed</span>
              )}
              <span className="tabular-nums text-sm text-slate-200">
                {formatMoney(item.total, item.currency)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}


function Attachments({ po, onChange, canWrite }) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);

  async function upload(event) {
    const file = event.target.files?.[0];
    event.target.value = "";          // so the same file can be picked again
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const body = new FormData();
      body.append("file", file);
      await api.post(`/api/purchase-orders/${po.id}/attachments`, body);
      await onChange();
    } catch (err) {
      setError(apiError(err, "Couldn't attach that file."));
    } finally {
      setUploading(false);
    }
  }

  async function remove(attachmentId) {
    try {
      await api.delete(`/api/purchase-orders/${po.id}/attachments/${attachmentId}`);
      await onChange();
    } catch (err) {
      setError(apiError(err, "Couldn't remove that file."));
    }
  }

  // Cancelled orders take no more files, and a read-only member adds none.
  const locked = po.status === "cancelled" || !canWrite;

  return (
    <div className="glass rounded-2xl p-5 sm:p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">Attachments</h2>
        {!locked && (
          <label
            className={cn(
              "inline-flex h-9 cursor-pointer items-center gap-1.5 rounded-lg border border-white/10 px-3 text-sm text-slate-300 hover:bg-white/[0.06] hover:text-white",
              uploading && "pointer-events-none opacity-60",
            )}
          >
            {uploading ? (
              <Loader2 size={15} className="animate-spin" />
            ) : (
              <Paperclip size={15} />
            )}
            Attach file
            <input
              type="file"
              className="hidden"
              onChange={upload}
              accept=".pdf,.jpg,.jpeg,.png,.xlsx,.xls,.csv,.txt"
            />
          </label>
        )}
      </div>

      {error && <p className="mt-3 text-xs text-rose-300">{error}</p>}

      {po.attachments.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">
          Quotes, specifications or a signed copy. Attachments stay available
          after approval — they describe the order rather than change it.
        </p>
      ) : (
        <ul className="mt-3 divide-y divide-white/[0.05]">
          {po.attachments.map((a) => (
            <li key={a.id} className="flex items-center gap-3 py-2.5">
              <Paperclip size={14} className="shrink-0 text-slate-500" />
              <button
                onClick={() =>
                  downloadFile(
                    `/api/purchase-orders/${po.id}/attachments/${a.id}`,
                    a.fileName,
                  )
                }
                className="min-w-0 flex-1 truncate text-left text-sm text-slate-200 hover:text-brand-200"
              >
                {a.fileName}
              </button>
              <span className="shrink-0 text-xs text-slate-600">
                {formatBytes(a.fileSize)}
              </span>
              {!locked && (
                <button
                  onClick={() => remove(a.id)}
                  className="grid h-7 w-7 shrink-0 place-items-center rounded-lg text-slate-500 hover:bg-rose-500/10 hover:text-rose-300"
                  title="Remove"
                >
                  <Trash2 size={14} />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* ── Who did what ──────────────────────────────────────────────────────────── */
function Trail({ po }) {
  const events = [
    ["Raised", po.createdAt, po.createdBy],
    ["Submitted for approval", po.submittedAt, null],
    ["Sent back for changes", po.rejectedAt, null],
    ["Approved", po.approvedAt, po.approvedBy],
    ["Sent to supplier", po.sentAt, null],
    ["Closed", po.closedAt, null],
    ["Cancelled", po.cancelledAt, null],
  ].filter(([, when]) => when);

  if (events.length === 0) return null;

  return (
    <div className="glass rounded-2xl p-5 sm:p-6">
      <h2 className="text-sm font-semibold text-white">History</h2>
      <ul className="mt-3 space-y-2 text-sm">
        {events.map(([label, when, who]) => (
          <li key={label} className="flex flex-wrap items-baseline gap-x-2">
            <span className="text-slate-200">{label}</span>
            <span className="text-xs text-slate-500">{formatDate(when)}</span>
            {who && (
              <span className="text-xs text-slate-500">
                · {who.name || who.email}
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function RejectDialog({ onClose, onReject, busy }) {
  const [reason, setReason] = useState("");

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4">
      <div className="glass w-full max-w-md rounded-2xl p-6">
        <div className="flex items-start justify-between">
          <h2 className="text-lg font-semibold text-white">Send back for changes</h2>
          <button onClick={onClose} className="text-slate-500 hover:text-white">
            <X size={18} />
          </button>
        </div>
        <p className="mt-2 text-sm text-slate-400">
          The order returns to draft. Say what needs to change — this is the only
          record of why it was refused.
        </p>
        <textarea
          rows={3}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Over budget for Q4 — reduce to 10 units."
          className="mt-3 w-full rounded-lg border border-white/10 bg-ink-900/60 p-2.5 text-sm text-white placeholder:text-slate-600 outline-none focus:border-brand-400/60"
        />
        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="h-10 rounded-lg px-4 text-sm text-slate-300 hover:bg-white/[0.06]"
          >
            Cancel
          </button>
          <Button
            onClick={() => onReject(reason)}
            disabled={busy || !reason.trim()}
          >
            {busy ? <Loader2 size={15} className="animate-spin" /> : <XCircle size={15} />}
            Reject
          </Button>
        </div>
      </div>
    </div>
  );
}

/** Drop trailing zeros from a decimal string: "3.0000" → "3", "2.5000" → "2.5".
 *  String work, never Number() — the point of the decimal strings is not to
 *  route money through a float, and trimming zeros loses nothing. */
function trimDecimal(value, fallback = "") {
  if (value === null || value === undefined || value === "") return fallback;
  const text = String(value);
  if (!text.includes(".")) return text;
  return text.replace(/\.?0+$/, "") || "0";
}

/** The same, for display, where an absent value should read as a dash. */
function trimQty(value) {
  return trimDecimal(value, "—");
}
