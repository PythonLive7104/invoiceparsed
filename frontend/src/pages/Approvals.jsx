import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  Bell,
  Check,
  ChevronLeft,
  ChevronRight,
  Loader2,
  MessageSquare,
  ShieldCheck,
  UserCheck,
  X,
} from "lucide-react";
import { api, apiError } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/lib/auth.jsx";
import { PERMISSIONS } from "@/lib/permissions";
import { cn, formatDate, formatMoney } from "@/lib/utils";
import {
  PAYABLES,
  PAYABLES_COPY,
  UpgradePanel,
} from "@/components/dashboard/UpgradePanel";
import {
  ApprovalBadge,
  ApprovalChain,
  EVENT_LABEL,
} from "@/components/dashboard/ApprovalStatus";

/**
 * Approvals: the queue, the rules behind it, and who is covering for whom.
 *
 * The default view is **mine** — what is waiting on the person reading the
 * page. An approvals screen that opens on everything is a screen people stop
 * opening, and the whole value of a workflow is that it reaches someone.
 *
 * Nothing here decides anything locally. Whether a person may act on a
 * request is `canAct`, which the server computes from the chain, the current
 * level and any delegation; re-deriving it in the browser would be a second
 * opinion about authority.
 */

const TABS = [
  ["mine", "Waiting on me"],
  ["open", "All open"],
  ["", "Everything"],
];

export default function Approvals() {
  const { can, has } = useAuth();
  const locked = !has(PAYABLES);
  const canAct = can(PERMISSIONS.approvalsAct);
  const canManageRules = can(PERMISSIONS.organizationSettings);

  const [tab, setTab] = useState("mine");
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [openId, setOpenId] = useState(null);
  const [panel, setPanel] = useState(null); // rules | delegations

  const load = useCallback(() => {
    if (locked) return undefined;
    let active = true;
    setLoading(true);
    const params = new URLSearchParams({ page: String(page), perPage: "25" });
    if (tab === "mine") params.set("mine", "1");
    else if (tab) params.set("status", tab);
    api
      .get(`/api/approvals/requests?${params}`)
      .then(({ data: body }) => active && setData(body))
      .catch(() => active && setData({ requests: [], total: 0 }))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [page, tab, locked]);

  useEffect(load, [load]);

  if (locked)
    return <UpgradePanel {...PAYABLES_COPY.approvals} icon={ShieldCheck} />;

  const rows = data?.requests ?? [];
  const pages = data?.pages ?? 1;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-white">
            Approvals
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            What is waiting on a decision, and the rules that decide who is
            asked.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            onClick={() => setPanel(panel === "delegations" ? null : "delegations")}
          >
            <UserCheck size={16} /> Delegation
          </Button>
          {canManageRules && (
            <Button
              variant="secondary"
              onClick={() => setPanel(panel === "rules" ? null : "rules")}
            >
              <ShieldCheck size={16} /> Rules
            </Button>
          )}
        </div>
      </div>

      {panel === "rules" && <RulesPanel onClose={() => setPanel(null)} />}
      {panel === "delegations" && (
        <DelegationPanel onClose={() => setPanel(null)} />
      )}

      <div className="flex flex-wrap gap-1.5">
        {TABS.map(([value, label]) => (
          <button
            key={value || "all"}
            onClick={() => {
              setTab(value);
              setPage(1);
            }}
            className={cn(
              "h-9 rounded-lg px-3 text-sm transition-colors",
              tab === value
                ? "bg-brand-500/15 text-brand-200"
                : "text-slate-400 hover:bg-white/[0.06] hover:text-white",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {loading && data === null ? (
        <div className="grid place-items-center py-20">
          <Loader2 className="animate-spin text-brand-400" size={26} />
        </div>
      ) : rows.length === 0 ? (
        <div className="glass flex flex-col items-center rounded-2xl px-6 py-16 text-center">
          <span className="grid h-14 w-14 place-items-center rounded-2xl bg-white/[0.04] text-slate-500">
            <ShieldCheck size={26} />
          </span>
          <h3 className="mt-5 text-lg font-semibold text-white">
            {tab === "mine" ? "Nothing waiting on you" : "No approvals yet"}
          </h3>
          <p className="mt-1.5 max-w-sm text-sm text-slate-400">
            {tab === "mine"
              ? "When something needs your decision it will appear here."
              : "Approval chains are built when an order is submitted and a rule matches it."}
          </p>
        </div>
      ) : (
        <div className={cn("space-y-3", loading && "opacity-60")}>
          {rows.map((row) => (
            <RequestRow
              key={row.id}
              row={row}
              expanded={openId === row.id}
              onToggle={() => setOpenId(openId === row.id ? null : row.id)}
              onChanged={load}
              canAct={canAct}
            />
          ))}

          {pages > 1 && (
            <div className="flex items-center justify-between px-1 text-xs text-slate-400">
              <span>
                Page {page} of {pages} · {data.total} request
                {data.total === 1 ? "" : "s"}
              </span>
              <div className="flex gap-1">
                <button
                  disabled={page <= 1}
                  onClick={() => setPage((v) => v - 1)}
                  className="grid h-7 w-7 place-items-center rounded-md border border-white/10 disabled:opacity-40"
                  aria-label="Previous page"
                >
                  <ChevronLeft size={14} />
                </button>
                <button
                  disabled={page >= pages}
                  onClick={() => setPage((v) => v + 1)}
                  className="grid h-7 w-7 place-items-center rounded-md border border-white/10 disabled:opacity-40"
                  aria-label="Next page"
                >
                  <ChevronRight size={14} />
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** One request in the queue, expanding into its chain, history and actions. */
function RequestRow({ row, expanded, onToggle, onChanged, canAct }) {
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [form, setForm] = useState(null); // reject | ask | answer

  const load = useCallback(() => {
    let active = true;
    api
      .get(`/api/approvals/requests/${row.id}`)
      .then(({ data }) => active && setDetail(data.approvalRequest))
      .catch(() => active && setError("Couldn't load this request."));
    return () => {
      active = false;
    };
  }, [row.id]);

  useEffect(() => {
    if (expanded && detail === null) load();
  }, [expanded, detail, load]);

  async function act(key, path, body) {
    setBusy(key);
    setError(null);
    try {
      const { data } = await api.post(
        `/api/approvals/requests/${row.id}/${path}`,
        body ?? {},
      );
      setDetail(data.approvalRequest);
      setForm(null);
      onChanged?.();
    } catch (err) {
      setError(apiError(err, "That didn't work."));
    } finally {
      setBusy(null);
    }
  }

  const subject = row.subject ?? {};
  const live = detail ?? row;

  return (
    <div
      className={cn(
        "glass overflow-hidden rounded-2xl",
        row.stuck && "border-rose-500/30",
      )}
    >
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full flex-wrap items-center gap-x-4 gap-y-2 px-5 py-4 text-left transition-colors hover:bg-white/[0.02]"
      >
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
            <span className="font-medium text-white">
              {subject.reference || row.subjectId}
            </span>
            {subject.supplierName && (
              <span className="text-sm text-slate-400">
                {subject.supplierName}
              </span>
            )}
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-500">
            {row.ruleName && <span>{row.ruleName}</span>}
            <span>·</span>
            <span>Level {row.currentLevel}</span>
            {row.submittedBy && (
              <>
                <span>·</span>
                <span>by {row.submittedBy}</span>
              </>
            )}
            {row.submittedAt && (
              <>
                <span>·</span>
                <span>{formatDate(row.submittedAt)}</span>
              </>
            )}
          </div>
        </div>

        {row.stuck && (
          <span
            className="inline-flex items-center gap-1 text-xs text-rose-300"
            title="Nobody is able to act on this"
          >
            <AlertTriangle size={12} /> Stuck
          </span>
        )}
        <span className="tabular-nums text-sm text-slate-200">
          {formatMoney(row.amount, row.currency)}
        </span>
        <ApprovalBadge status={row.status} />
      </button>

      {expanded && (
        <div className="border-t border-white/[0.06] px-5 py-4">
          {detail === null ? (
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <Loader2 size={13} className="animate-spin" /> Loading…
            </div>
          ) : (
            <>
              {live.stuck && (
                <p className="mb-4 rounded-lg border border-rose-400/25 bg-rose-500/10 px-3 py-2 text-xs leading-relaxed text-rose-100">
                  Nobody is currently able to act on this — the approvers at
                  this level have all left or no longer hold the role. An
                  administrator can cancel it and resubmit under a rule that
                  names somebody who is still here.
                </p>
              )}

              {subject.id && subject.kind === "purchase_order" && (
                <Link
                  to={`/dashboard/purchase-orders/${subject.id}`}
                  className="mb-4 inline-block text-sm text-indigo-300 hover:text-indigo-200"
                >
                  Open {subject.reference} →
                </Link>
              )}

              <ApprovalChain
                steps={live.steps}
                currentLevel={live.currentLevel}
              />

              {live.history?.length > 0 && (
                <div className="mt-5">
                  <h4 className="text-xs font-medium uppercase tracking-wider text-slate-500">
                    History
                  </h4>
                  <ul className="mt-2 space-y-1.5">
                    {live.history.map((event) => (
                      <li
                        key={event.id}
                        className="flex flex-wrap items-baseline gap-x-2 text-xs text-slate-400"
                      >
                        <span className="text-slate-300">
                          {EVENT_LABEL[event.action] ?? event.action}
                        </span>
                        {event.by && <span>by {event.by}</span>}
                        {event.target && <span>→ {event.target}</span>}
                        <span className="text-slate-600">
                          {formatDate(event.at)}
                        </span>
                        {event.comment && (
                          <span className="w-full italic text-slate-500">
                            “{event.comment}”
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {error && <p className="mt-3 text-sm text-rose-300">{error}</p>}

              {form && (
                <CommentForm
                  kind={form}
                  busy={busy === form}
                  onCancel={() => setForm(null)}
                  onSubmit={(text) => {
                    if (form === "reject") act("reject", "reject", { reason: text });
                    else if (form === "ask") act("ask", "ask", { question: text });
                    else act("answer", "answer", { answer: text });
                  }}
                />
              )}

              {live.isOpen && !form && (
                <div className="mt-4 flex flex-wrap gap-2">
                  {canAct && live.canAct && (
                    <>
                      <button
                        type="button"
                        disabled={busy === "approve"}
                        onClick={() => act("approve", "approve")}
                        className="inline-flex items-center gap-1.5 rounded-md border border-emerald-400/40 bg-emerald-500/15 px-3 py-1.5 text-xs font-medium text-emerald-200 transition-colors hover:bg-emerald-500/25 disabled:opacity-50"
                      >
                        {busy === "approve" ? (
                          <Loader2 size={12} className="animate-spin" />
                        ) : (
                          <Check size={12} />
                        )}
                        Approve
                      </button>
                      <button
                        type="button"
                        onClick={() => setForm("reject")}
                        className="inline-flex items-center gap-1.5 rounded-md border border-rose-400/40 bg-rose-500/15 px-3 py-1.5 text-xs font-medium text-rose-200 transition-colors hover:bg-rose-500/25"
                      >
                        <X size={12} /> Reject
                      </button>
                      <button
                        type="button"
                        onClick={() => setForm("ask")}
                        className="inline-flex items-center gap-1.5 rounded-md border border-white/15 px-3 py-1.5 text-xs font-medium text-slate-300 transition-colors hover:bg-white/5"
                      >
                        <MessageSquare size={12} /> Ask a question
                      </button>
                    </>
                  )}
                  {live.status === "info_requested" && (
                    <button
                      type="button"
                      onClick={() => setForm("answer")}
                      className="inline-flex items-center gap-1.5 rounded-md border border-amber-400/40 bg-amber-500/15 px-3 py-1.5 text-xs font-medium text-amber-100 transition-colors hover:bg-amber-500/25"
                    >
                      <MessageSquare size={12} /> Answer
                    </button>
                  )}
                  <button
                    type="button"
                    disabled={busy === "remind"}
                    onClick={() => act("remind", "remind")}
                    className="inline-flex items-center gap-1.5 rounded-md border border-white/15 px-3 py-1.5 text-xs font-medium text-slate-400 transition-colors hover:bg-white/5 disabled:opacity-50"
                  >
                    <Bell size={12} /> Remind
                  </button>
                </div>
              )}

              {live.isOpen && canAct && !live.canAct && !form && (
                <p className="mt-3 text-xs text-slate-500">
                  This is waiting on{" "}
                  {live.waitingOn?.filter(Boolean).join(", ") || "somebody else"}.
                </p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

const PROMPTS = {
  reject: {
    label: "Why are you rejecting this?",
    hint: "The person who raised it sees this, so say what to change.",
    cta: "Reject",
  },
  ask: {
    label: "What do you need to know?",
    hint: "The request stays assigned to you while you wait for an answer.",
    cta: "Send question",
  },
  answer: {
    label: "Your answer",
    hint: "This puts the request back in the approver's queue.",
    cta: "Send answer",
  },
};

function CommentForm({ kind, busy, onSubmit, onCancel }) {
  const [text, setText] = useState("");
  const prompt = PROMPTS[kind];
  return (
    <form
      className="mt-4 rounded-xl border border-white/10 bg-ink-950/40 p-3"
      onSubmit={(event) => {
        event.preventDefault();
        if (text.trim()) onSubmit(text.trim());
      }}
    >
      <label className="block text-xs font-medium text-slate-300">
        {prompt.label}
      </label>
      <p className="mt-0.5 text-xs text-slate-500">{prompt.hint}</p>
      <textarea
        value={text}
        onChange={(event) => setText(event.target.value)}
        rows={2}
        maxLength={1000}
        autoFocus
        className="mt-2 w-full rounded-md border border-white/10 bg-ink-950/60 px-2.5 py-1.5 text-xs text-white placeholder:text-slate-600 focus:border-brand-400/50 focus:outline-none"
      />
      <div className="mt-2 flex gap-2">
        <Button type="submit" size="sm" disabled={busy || !text.trim()}>
          {busy && <Loader2 size={13} className="animate-spin" />}
          {prompt.cta}
        </Button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md border border-white/15 px-3 py-1.5 text-xs font-medium text-slate-300 transition-colors hover:bg-white/5"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

/* ── Rules ───────────────────────────────────────────────────────────────── */
const ROLES = [
  "owner", "administrator", "finance_manager", "accountant",
  "procurement_officer", "department_manager", "approver",
];

function RulesPanel({ onClose }) {
  const [rules, setRules] = useState(null);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    let active = true;
    api
      .get("/api/approvals/rules")
      .then(({ data }) => active && setRules(data.rules ?? []))
      .catch((err) => active && setError(apiError(err, "Couldn't load rules.")));
    return () => {
      active = false;
    };
  }, []);

  useEffect(load, [load]);

  async function deactivate(id) {
    try {
      await api.delete(`/api/approvals/rules/${id}`);
      load();
    } catch (err) {
      setError(apiError(err, "Couldn't deactivate that rule."));
    }
  }

  return (
    <div className="glass rounded-2xl p-5 sm:p-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-white">Approval rules</h2>
          <p className="mt-1 text-sm text-slate-400">
            The highest-priority matching rule applies, and only that one.
            Conditions you leave blank do not constrain — a rule with none
            matches everything.
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="text-slate-500 transition-colors hover:text-slate-300"
          aria-label="Close"
        >
          <X size={16} />
        </button>
      </div>

      {error && <p className="mt-3 text-sm text-rose-300">{error}</p>}

      {rules === null ? (
        <Loader2 className="mt-4 animate-spin text-brand-400" size={18} />
      ) : (
        <ul className="mt-4 space-y-2">
          {rules.filter((rule) => rule.active).length === 0 && !adding && (
            <li className="rounded-xl border border-white/[0.06] p-4 text-sm text-slate-400">
              No rules yet. Orders are approved by any one person who can
              approve — add a rule to require more.
            </li>
          )}
          {rules
            .filter((rule) => rule.active)
            .map((rule) => (
              <li
                key={rule.id}
                className="rounded-xl border border-white/[0.06] p-4"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium text-white">{rule.name}</span>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-slate-500">
                      priority {rule.priority}
                    </span>
                    <button
                      type="button"
                      onClick={() => deactivate(rule.id)}
                      className="text-xs text-slate-400 transition-colors hover:text-rose-300"
                    >
                      Deactivate
                    </button>
                  </div>
                </div>
                <p className="mt-1 text-xs text-slate-500">
                  {describe(rule.conditions)}
                </p>
                <ul className="mt-2 space-y-0.5 text-xs text-slate-400">
                  {rule.steps.map((step) => (
                    <li key={step.id}>
                      Level {step.level}:{" "}
                      {step.approverRole?.replace(/_/g, " ") ?? "a named person"}
                      {step.requireAll && " (all must approve)"}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
        </ul>
      )}

      {adding ? (
        <RuleForm
          onCancel={() => setAdding(false)}
          onSaved={() => {
            setAdding(false);
            load();
          }}
        />
      ) : (
        <Button className="mt-4" variant="secondary" onClick={() => setAdding(true)}>
          Add a rule
        </Button>
      )}
    </div>
  );
}

/** A rule's conditions, in words. "Applies to everything" is a real answer. */
function describe(conditions) {
  const parts = [];
  if (conditions.minAmount && Number(conditions.minAmount) > 0)
    parts.push(`${conditions.minAmount} or more`);
  if (conditions.maxAmount && Number(conditions.maxAmount) > 0)
    parts.push(`up to ${conditions.maxAmount}`);
  if (conditions.currency) parts.push(`in ${conditions.currency}`);
  if (conditions.department) parts.push(`department ${conditions.department}`);
  if (conditions.costCenter) parts.push(`cost centre ${conditions.costCenter}`);
  if (conditions.project) parts.push(`project ${conditions.project}`);
  if (conditions.category) parts.push(`category ${conditions.category}`);
  if (conditions.supplierName) parts.push(`supplier ${conditions.supplierName}`);
  return parts.length ? `Applies to orders ${parts.join(", ")}.`
    : "Applies to every order.";
}

function RuleForm({ onCancel, onSaved }) {
  const [form, setForm] = useState({
    name: "", minAmount: "", maxAmount: "", department: "", priority: "0",
  });
  const [steps, setSteps] = useState([
    { level: 1, approverRole: "finance_manager", requireAll: false },
  ]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [fields, setFields] = useState({});

  async function save(event) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setFields({});
    try {
      await api.post("/api/approvals/rules", {
        ...form,
        subjectType: "purchase_order",
        priority: Number(form.priority) || 0,
        steps: steps.map((step) => ({
          level: step.level,
          approverType: "role",
          approverRole: step.approverRole,
          requireAll: step.requireAll,
        })),
      });
      onSaved();
    } catch (err) {
      setFields(err?.response?.data?.fields ?? {});
      setError(apiError(err, "Couldn't save that rule."));
    } finally {
      setSaving(false);
    }
  }

  function set(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  return (
    <form onSubmit={save} className="mt-4 rounded-xl border border-white/10 bg-ink-950/40 p-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Name" value={form.name} error={fields.name}
          onChange={(v) => set("name", v)} placeholder="Spend over 500,000" />
        <Field label="Priority" value={form.priority} error={fields.priority}
          onChange={(v) => set("priority", v)}
          hint="Higher wins where two rules match." />
        <Field label="Minimum amount" value={form.minAmount}
          error={fields.minAmount} onChange={(v) => set("minAmount", v)}
          placeholder="Any" />
        <Field label="Maximum amount" value={form.maxAmount}
          error={fields.maxAmount} onChange={(v) => set("maxAmount", v)}
          placeholder="Any" />
        <Field label="Department" value={form.department}
          error={fields.department} onChange={(v) => set("department", v)}
          placeholder="Any" />
      </div>

      <div className="mt-4">
        <span className="text-xs font-medium text-slate-300">
          Who must approve
        </span>
        <p className="mt-0.5 text-xs text-slate-500">
          Levels run in order. Level 2 is not asked until level 1 is satisfied.
        </p>
        <ul className="mt-2 space-y-2">
          {steps.map((step, index) => (
            <li key={index} className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-slate-500">Level</span>
              <input
                value={step.level}
                onChange={(event) =>
                  setSteps((current) =>
                    current.map((s, i) =>
                      i === index
                        ? { ...s, level: Number(event.target.value) || 1 }
                        : s,
                    ),
                  )
                }
                className="h-9 w-14 rounded-lg border border-white/10 bg-ink-950/60 px-2 text-sm tabular-nums text-white outline-none focus:border-brand-400/60"
              />
              <select
                value={step.approverRole}
                onChange={(event) =>
                  setSteps((current) =>
                    current.map((s, i) =>
                      i === index ? { ...s, approverRole: event.target.value } : s,
                    ),
                  )
                }
                className="h-9 rounded-lg border border-white/10 bg-ink-950/60 px-2 text-sm text-white outline-none focus:border-brand-400/60"
              >
                {ROLES.map((role) => (
                  <option key={role} value={role}>
                    {role.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
              <label className="flex items-center gap-1.5 text-xs text-slate-400">
                <input
                  type="checkbox"
                  checked={step.requireAll}
                  onChange={(event) =>
                    setSteps((current) =>
                      current.map((s, i) =>
                        i === index
                          ? { ...s, requireAll: event.target.checked }
                          : s,
                      ),
                    )
                  }
                  className="size-3.5 rounded border-white/20 bg-ink-900 accent-brand-500"
                />
                all must approve
              </label>
              {steps.length > 1 && (
                <button
                  type="button"
                  onClick={() =>
                    setSteps((current) => current.filter((_, i) => i !== index))
                  }
                  className="text-slate-500 transition-colors hover:text-rose-300"
                  aria-label="Remove step"
                >
                  <X size={13} />
                </button>
              )}
            </li>
          ))}
        </ul>
        <button
          type="button"
          onClick={() =>
            setSteps((current) => [
              ...current,
              {
                level: Math.max(...current.map((s) => s.level)) + 1,
                approverRole: "administrator",
                requireAll: false,
              },
            ])
          }
          className="mt-2 text-xs text-indigo-300 transition-colors hover:text-indigo-200"
        >
          + Add a level
        </button>
        {fields.steps && (
          <p className="mt-1 text-xs text-rose-300">{fields.steps}</p>
        )}
      </div>

      {error && <p className="mt-3 text-sm text-rose-300">{error}</p>}

      <div className="mt-4 flex gap-2">
        <Button type="submit" size="sm" disabled={saving}>
          {saving && <Loader2 size={13} className="animate-spin" />}
          Save rule
        </Button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md border border-white/15 px-3 py-1.5 text-xs font-medium text-slate-300 transition-colors hover:bg-white/5"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

function Field({ label, value, onChange, error, hint, ...rest }) {
  return (
    <label className="block">
      <span className="text-xs text-slate-400">{label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={cn(
          "mt-1 h-10 w-full rounded-lg border bg-ink-950/60 px-3 text-sm text-white placeholder:text-slate-600 outline-none",
          error ? "border-rose-500/50" : "border-white/10 focus:border-brand-400/60",
        )}
        {...rest}
      />
      {(error || hint) && (
        <span
          className={cn("mt-1 block text-xs",
            error ? "text-rose-300" : "text-slate-500")}
        >
          {error || hint}
        </span>
      )}
    </label>
  );
}

/* ── Delegation ──────────────────────────────────────────────────────────── */
function DelegationPanel({ onClose }) {
  const [rows, setRows] = useState(null);
  const [people, setPeople] = useState([]);
  const [form, setForm] = useState({ toUserId: "", startsOn: "", endsOn: "",
                                     reason: "" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    let active = true;
    api
      .get("/api/approvals/delegations")
      .then(({ data }) => active && setRows(data.delegations ?? []))
      .catch(() => active && setRows([]));
    api
      .get("/api/organizations/current/members")
      .then(({ data }) => active && setPeople(data.members ?? []))
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  useEffect(load, [load]);

  async function save(event) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await api.post("/api/approvals/delegations", form);
      setForm({ toUserId: "", startsOn: "", endsOn: "", reason: "" });
      load();
    } catch (err) {
      setError(apiError(err, "Couldn't set up that delegation."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="glass rounded-2xl p-5 sm:p-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-white">Delegation</h2>
          <p className="mt-1 text-sm text-slate-400">
            Let somebody approve in your place while you are away. Both names
            stay on every decision they make for you.
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="text-slate-500 transition-colors hover:text-slate-300"
          aria-label="Close"
        >
          <X size={16} />
        </button>
      </div>

      {rows === null ? (
        <Loader2 className="mt-4 animate-spin text-brand-400" size={18} />
      ) : rows.filter((row) => row.active).length > 0 ? (
        <ul className="mt-4 space-y-2">
          {rows
            .filter((row) => row.active)
            .map((row) => (
              <li
                key={row.id}
                className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-white/[0.06] p-3 text-sm"
              >
                <span className="text-slate-200">
                  {row.from} → {row.to}
                </span>
                <span className="text-xs text-slate-500">
                  {row.startsOn || "now"} – {row.endsOn || "no end date"}
                </span>
                {row.reason && (
                  <span className="text-xs italic text-slate-500">
                    {row.reason}
                  </span>
                )}
                <button
                  type="button"
                  onClick={async () => {
                    await api.delete(`/api/approvals/delegations/${row.id}`);
                    load();
                  }}
                  className="ml-auto text-xs text-slate-400 transition-colors hover:text-rose-300"
                >
                  End
                </button>
              </li>
            ))}
        </ul>
      ) : (
        <p className="mt-4 text-sm text-slate-500">
          Nothing delegated at the moment.
        </p>
      )}

      <form onSubmit={save} className="mt-4 grid gap-3 sm:grid-cols-4">
        <label className="block sm:col-span-2">
          <span className="text-xs text-slate-400">Approve in my place</span>
          <select
            value={form.toUserId}
            onChange={(event) =>
              setForm((f) => ({ ...f, toUserId: event.target.value }))
            }
            className="mt-1 h-10 w-full rounded-lg border border-white/10 bg-ink-950/60 px-3 text-sm text-white outline-none focus:border-brand-400/60"
          >
            <option value="">Choose a colleague…</option>
            {people.map((person) => (
              <option key={person.userId ?? person.id} value={person.userId ?? person.id}>
                {person.name || person.email}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="text-xs text-slate-400">From</span>
          <input
            type="date"
            value={form.startsOn}
            onChange={(event) =>
              setForm((f) => ({ ...f, startsOn: event.target.value }))
            }
            className="mt-1 h-10 w-full rounded-lg border border-white/10 bg-ink-950/60 px-3 text-sm text-white outline-none focus:border-brand-400/60"
          />
        </label>
        <label className="block">
          <span className="text-xs text-slate-400">Until</span>
          <input
            type="date"
            value={form.endsOn}
            onChange={(event) =>
              setForm((f) => ({ ...f, endsOn: event.target.value }))
            }
            className="mt-1 h-10 w-full rounded-lg border border-white/10 bg-ink-950/60 px-3 text-sm text-white outline-none focus:border-brand-400/60"
          />
        </label>
        <div className="sm:col-span-4">
          {error && <p className="mb-2 text-sm text-rose-300">{error}</p>}
          <Button type="submit" size="sm" disabled={saving || !form.toUserId}>
            {saving && <Loader2 size={13} className="animate-spin" />}
            Delegate
          </Button>
          <p className="mt-2 text-xs text-slate-500">
            Leaving the end date blank makes this open-ended. A date is better:
            an open delegation outlives the holiday it was created for.
          </p>
        </div>
      </form>
    </div>
  );
}
