import { useEffect, useState } from "react";
import {
  KeyRound,
  Webhook,
  Plus,
  Trash2,
  Copy,
  Check,
  Loader2,
  Lock,
  Send,
  Terminal,
  ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/lib/auth.jsx";
import { planAllows } from "@/lib/plans";
import { cn, formatDate } from "@/lib/utils";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:5000";

export default function ApiSettings() {
  const { user } = useAuth();
  const isPro = planAllows(user?.plan, "api");

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-white sm:text-3xl">
          API & Webhooks
        </h1>
        <p className="mt-1.5 text-slate-400">
          Extract invoices programmatically and get results pushed to your systems.
        </p>
      </div>

      {!isPro ? (
        <UpgradeGate />
      ) : (
        <>
          <ApiKeysSection />
          <WebhooksSection />
          <DocsSection />
        </>
      )}
    </div>
  );
}

function UpgradeGate() {
  return (
    <div className="glass flex flex-col items-center justify-center rounded-2xl px-6 py-16 text-center">
      <span className="grid h-14 w-14 place-items-center rounded-2xl bg-brand-500/15 text-brand-300 ring-1 ring-inset ring-brand-400/20">
        <Lock size={24} />
      </span>
      <h3 className="mt-5 text-lg font-semibold text-white">API access is a Pro feature</h3>
      <p className="mt-1.5 max-w-md text-sm text-slate-400">
        Upgrade to Pro to create API keys, extract invoices programmatically, and receive
        webhook callbacks when extractions complete.
      </p>
      <Button to="/dashboard/billing" className="mt-6">
        Upgrade to Pro
      </Button>
    </div>
  );
}

function CopyButton({ text, label = "Copy" }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      className="inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium text-slate-300 transition-colors hover:bg-white/[0.06]"
    >
      {copied ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
      {copied ? "Copied" : label}
    </button>
  );
}

function Section({ icon, title, desc, children, action }) {
  return (
    <div className="glass rounded-2xl p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-brand-500/15 text-brand-300 ring-1 ring-inset ring-brand-400/20">
            {icon}
          </span>
          <div>
            <h2 className="text-lg font-semibold text-white">{title}</h2>
            <p className="mt-0.5 text-sm text-slate-400">{desc}</p>
          </div>
        </div>
        {action}
      </div>
      <div className="mt-5">{children}</div>
    </div>
  );
}

function ApiKeysSection() {
  const [keys, setKeys] = useState(null);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState(null); // full key shown once
  const [error, setError] = useState(null);

  useEffect(() => {
    api.get("/api/keys").then(({ data }) => setKeys(data.keys)).catch(() => setKeys([]));
  }, []);

  async function create() {
    setCreating(true);
    setError(null);
    try {
      const { data } = await api.post("/api/keys", { name: name.trim() || "API key" });
      setCreated(data.key);
      setKeys((prev) => [data.apiKey, ...(prev || [])]);
      setName("");
    } catch (err) {
      setError(apiError(err));
    }
    setCreating(false);
  }

  async function revoke(id) {
    if (!confirm("Revoke this API key? Apps using it will stop working immediately.")) return;
    await api.delete(`/api/keys/${id}`).catch(() => {});
    setKeys((prev) => prev.filter((k) => k.id !== id));
  }

  return (
    <Section
      icon={<KeyRound size={19} />}
      title="API keys"
      desc="Authenticate requests with a secret key. Treat keys like passwords."
    >
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Key name (e.g. Production)"
          className="h-11 flex-1 rounded-xl border border-white/10 bg-ink-900/60 px-3.5 text-sm text-white placeholder:text-slate-600 outline-none focus:border-brand-400/60 focus:ring-2 focus:ring-brand-400/20"
        />
        <Button onClick={create} disabled={creating}>
          {creating ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />}
          Create key
        </Button>
      </div>
      {error && <p className="mt-2 text-sm text-red-300">{error}</p>}

      {created && (
        <div className="mt-4 rounded-xl border border-emerald-500/30 bg-emerald-500/[0.07] p-4">
          <p className="text-xs font-medium text-emerald-200">
            Copy your new key now — you won't be able to see it again.
          </p>
          <div className="mt-2 flex items-center gap-2 rounded-lg bg-ink-950/70 px-3 py-2">
            <code className="min-w-0 flex-1 truncate font-mono text-sm text-emerald-300">{created}</code>
            <CopyButton text={created} />
          </div>
        </div>
      )}

      <div className="mt-5">
        {keys === null ? (
          <div className="grid place-items-center py-8">
            <Loader2 className="animate-spin text-brand-400" size={20} />
          </div>
        ) : keys.length === 0 ? (
          <p className="py-6 text-center text-sm text-slate-500">No API keys yet.</p>
        ) : (
          <div className="divide-y divide-white/[0.05]">
            {keys.map((k) => (
              <div key={k.id} className="flex items-center gap-3 py-3">
                <KeyRound size={16} className="shrink-0 text-slate-500" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium text-white">{k.name}</div>
                  <div className="truncate font-mono text-xs text-slate-500">
                    {k.prefix}••••••••••  · created {formatDate(k.createdAt)}
                    {k.lastUsedAt ? ` · last used ${formatDate(k.lastUsedAt)}` : " · never used"}
                  </div>
                </div>
                <button
                  onClick={() => revoke(k.id)}
                  className="grid h-8 w-8 place-items-center rounded-lg text-slate-400 transition-colors hover:bg-red-500/15 hover:text-red-300"
                  title="Revoke"
                >
                  <Trash2 size={15} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </Section>
  );
}

function WebhooksSection() {
  const [hooks, setHooks] = useState(null);
  const [url, setUrl] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState(null);
  const [testing, setTesting] = useState(null);
  const [testResult, setTestResult] = useState({}); // id -> status text

  useEffect(() => {
    api.get("/api/webhooks").then(({ data }) => setHooks(data.webhooks)).catch(() => setHooks([]));
  }, []);

  async function add() {
    setAdding(true);
    setError(null);
    try {
      const { data } = await api.post("/api/webhooks", { url: url.trim() });
      setHooks((prev) => [data.webhook, ...(prev || [])]);
      setUrl("");
    } catch (err) {
      setError(apiError(err));
    }
    setAdding(false);
  }

  async function remove(id) {
    if (!confirm("Delete this webhook?")) return;
    await api.delete(`/api/webhooks/${id}`).catch(() => {});
    setHooks((prev) => prev.filter((w) => w.id !== id));
  }

  async function test(id) {
    setTesting(id);
    try {
      const { data } = await api.post(`/api/webhooks/${id}/test`);
      setTestResult((prev) => ({
        ...prev,
        [id]: data.delivered ? `Delivered (HTTP ${data.status})` : `Failed (HTTP ${data.status})`,
      }));
    } catch {
      setTestResult((prev) => ({ ...prev, [id]: "Failed to send" }));
    }
    setTesting(null);
  }

  return (
    <Section
      icon={<Webhook size={19} />}
      title="Webhooks"
      desc="We POST a signed payload to your URL whenever an extraction completes."
    >
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://your-app.com/webhooks/invoiceparsed"
          className="h-11 flex-1 rounded-xl border border-white/10 bg-ink-900/60 px-3.5 text-sm text-white placeholder:text-slate-600 outline-none focus:border-brand-400/60 focus:ring-2 focus:ring-brand-400/20"
        />
        <Button onClick={add} disabled={adding}>
          {adding ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />}
          Add endpoint
        </Button>
      </div>
      {error && <p className="mt-2 text-sm text-red-300">{error}</p>}

      <div className="mt-5">
        {hooks === null ? (
          <div className="grid place-items-center py-8">
            <Loader2 className="animate-spin text-brand-400" size={20} />
          </div>
        ) : hooks.length === 0 ? (
          <p className="py-6 text-center text-sm text-slate-500">No webhook endpoints yet.</p>
        ) : (
          <div className="space-y-3">
            {hooks.map((w) => (
              <div key={w.id} className="rounded-xl border border-white/[0.07] bg-white/[0.02] p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium text-white">{w.url}</div>
                    <div className="mt-0.5 text-xs text-slate-500">
                      {w.lastStatus == null
                        ? "Never delivered"
                        : `Last delivery: HTTP ${w.lastStatus} · ${formatDate(w.lastDeliveryAt)}`}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <button
                      onClick={() => test(w.id)}
                      disabled={testing === w.id}
                      className="inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium text-slate-300 transition-colors hover:bg-white/[0.06]"
                    >
                      {testing === w.id ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />}
                      Test
                    </button>
                    <button
                      onClick={() => remove(w.id)}
                      className="grid h-8 w-8 place-items-center rounded-lg text-slate-400 transition-colors hover:bg-red-500/15 hover:text-red-300"
                      title="Delete"
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </div>

                <div className="mt-3 flex items-center gap-2 rounded-lg bg-ink-950/60 px-3 py-2">
                  <span className="text-xs text-slate-500">Signing secret</span>
                  <code className="min-w-0 flex-1 truncate font-mono text-xs text-slate-300">{w.secret}</code>
                  <CopyButton text={w.secret} />
                </div>

                {testResult[w.id] && (
                  <p
                    className={cn(
                      "mt-2 text-xs",
                      testResult[w.id].startsWith("Delivered") ? "text-emerald-300" : "text-red-300",
                    )}
                  >
                    {testResult[w.id]}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </Section>
  );
}

function DocsSection() {
  const curl = `curl -X POST ${API_URL}/api/extract \\
  -H "Authorization: Bearer ip_live_..." \\
  -F "file=@invoice.pdf"`;

  return (
    <Section
      icon={<Terminal size={19} />}
      title="Quick start"
      desc="Send a file, get structured JSON back. Use any API key above."
    >
      <div className="overflow-hidden rounded-xl border border-white/10 bg-ink-950/70">
        <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-2">
          <span className="text-[11px] text-slate-500">Extract an invoice</span>
          <CopyButton text={curl} />
        </div>
        <pre className="overflow-x-auto p-4 font-mono text-[12.5px] leading-relaxed text-slate-300">{curl}</pre>
      </div>

      <div className="mt-4 flex items-start gap-2.5 rounded-xl border border-white/[0.07] bg-white/[0.02] p-4 text-sm text-slate-400">
        <ShieldCheck size={16} className="mt-0.5 shrink-0 text-brand-300" />
        <span>
          Webhook requests are signed with{" "}
          <code className="rounded bg-white/[0.06] px-1 py-0.5 font-mono text-xs text-slate-300">
            X-InvoiceParsed-Signature: sha256=&lt;hmac&gt;
          </code>{" "}
          — verify it against your endpoint's signing secret using the raw request body.
        </span>
      </div>
    </Section>
  );
}
