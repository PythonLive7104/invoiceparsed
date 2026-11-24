import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  User as UserIcon,
  Mail,
  Lock,
  CreditCard,
  ShieldAlert,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Building2,
  Globe,
  Coins,
  Receipt,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { api } from "@/lib/api";
import { useAuth, apiError } from "@/lib/auth.jsx";
import { PERMISSIONS } from "@/lib/permissions";
import { formatDate } from "@/lib/utils";

export default function Settings() {
  const { user } = useAuth();
  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-white">Settings</h1>
        <p className="mt-1 text-sm text-slate-400">
          Manage your organization, profile, password and account.
        </p>
      </header>

      <OrganizationCard />
      <ProfileCard />
      <PasswordCard hasPassword={user?.hasPassword} />
      <PlanCard />
      <DangerZone />
    </div>
  );
}

function Card({ icon: Icon, title, description, children }) {
  return (
    <section className="glass rounded-2xl p-6">
      <div className="flex items-start gap-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-brand-500/15 text-brand-300">
          <Icon size={18} />
        </span>
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-white">{title}</h2>
          {description && <p className="mt-0.5 text-sm text-slate-400">{description}</p>}
        </div>
      </div>
      <div className="mt-5">{children}</div>
    </section>
  );
}

function Notice({ kind, children }) {
  if (!children) return null;
  const ok = kind === "ok";
  return (
    <div
      className={`flex items-start gap-2 rounded-lg border px-3 py-2.5 text-sm ${
        ok
          ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
          : "border-red-500/30 bg-red-500/10 text-red-300"
      }`}
    >
      {ok ? <CheckCircle2 size={16} className="mt-0.5 shrink-0" /> : <AlertCircle size={16} className="mt-0.5 shrink-0" />}
      {children}
    </div>
  );
}

function Field({ icon, label, ...rest }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-slate-300">{label}</span>
      <span className="relative block">
        {icon && (
          <span className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500">
            {icon}
          </span>
        )}
        <input
          className="h-11 w-full rounded-xl border border-white/10 bg-ink-900/60 pl-10 pr-3.5 text-sm text-white placeholder:text-slate-600 outline-none transition-colors focus:border-brand-400/60 focus:ring-2 focus:ring-brand-400/20 disabled:opacity-60"
          {...rest}
        />
      </span>
    </label>
  );
}

/**
 * The organization's own details, as distinct from the signed-in person's.
 *
 * Country, currency and tax ID are what exports and reports are built on, and
 * the getting-started checklist sends people here to fill them in — so this
 * card existing is what makes that step reachable at all.
 *
 * Loaded from the server rather than from the auth context: the context holds
 * the organization for the header, but these fields change here and nowhere
 * else, and re-reading on mount is cheaper than keeping a second copy in sync.
 */
function OrganizationCard() {
  const { can } = useAuth();
  const editable = can(PERMISSIONS.organizationSettings);

  const [form, setForm] = useState(null);
  const [saved, setSaved] = useState(null);
  const [loading, setLoading] = useState(false);
  const [ok, setOk] = useState(false);
  const [error, setError] = useState(null);
  const [fields, setFields] = useState({});

  useEffect(() => {
    let active = true;
    api
      .get("/api/organizations/current")
      .then(({ data }) => {
        if (!active) return;
        const next = {
          name: data.organization?.name ?? "",
          country: data.organization?.country ?? "",
          currency: data.organization?.currency ?? "",
          taxId: data.organization?.taxId ?? "",
        };
        setForm(next);
        setSaved(next);
      })
      .catch(() => active && setError("Couldn't load your organization."));
    return () => {
      active = false;
    };
  }, []);

  function set(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
    setOk(false);
  }

  async function onSave(event) {
    event.preventDefault();
    setLoading(true);
    setOk(false);
    setError(null);
    setFields({});
    try {
      const { data } = await api.patch("/api/organizations/current", {
        name: form.name.trim(),
        // Sent uppercased so what is stored matches what is shown; the server
        // uppercases too, and agreeing with it avoids the field appearing to
        // change by itself after a save.
        country: form.country.trim().toUpperCase(),
        currency: form.currency.trim().toUpperCase(),
        taxId: form.taxId.trim(),
      });
      const next = {
        name: data.organization?.name ?? "",
        country: data.organization?.country ?? "",
        currency: data.organization?.currency ?? "",
        taxId: data.organization?.taxId ?? "",
      };
      setForm(next);
      setSaved(next);
      setOk(true);
    } catch (err) {
      setFields(err?.response?.data?.fields ?? {});
      setError(apiError(err, "Couldn't save your business details."));
    } finally {
      setLoading(false);
    }
  }

  if (!form) {
    return (
      <Card
        icon={Building2}
        title="Organization"
        description="Your business details, used on exports and reports."
      >
        {error ? (
          <Notice kind="err">{error}</Notice>
        ) : (
          <Loader2 size={18} className="animate-spin text-brand-400" />
        )}
      </Card>
    );
  }

  const unchanged =
    saved &&
    ["name", "country", "currency", "taxId"].every(
      (key) => form[key].trim() === saved[key],
    );

  return (
    <Card
      icon={Building2}
      title="Organization"
      description="Your business details. These appear on exports and reports."
    >
      <form onSubmit={onSave} className="space-y-4">
        <Field
          icon={<Building2 size={16} />}
          label="Organization name"
          value={form.name}
          onChange={(event) => set("name", event.target.value)}
          placeholder="Acme Ltd"
          disabled={!editable}
        />
        {fields.name && <p className="-mt-2 text-xs text-red-300">{fields.name}</p>}

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <Field
              icon={<Globe size={16} />}
              label="Country"
              value={form.country}
              onChange={(event) => set("country", event.target.value.toUpperCase())}
              placeholder="NG"
              maxLength={2}
              disabled={!editable}
            />
            <p className="mt-1.5 text-xs text-slate-500">
              {fields.country ? (
                <span className="text-red-300">{fields.country}</span>
              ) : (
                "Two-letter code, e.g. NG, GB, US."
              )}
            </p>
          </div>
          <div>
            <Field
              icon={<Coins size={16} />}
              label="Default currency"
              value={form.currency}
              onChange={(event) => set("currency", event.target.value.toUpperCase())}
              placeholder="NGN"
              maxLength={3}
              disabled={!editable}
            />
            <p className="mt-1.5 text-xs text-slate-500">
              {fields.currency ? (
                <span className="text-red-300">{fields.currency}</span>
              ) : (
                "Three-letter code, e.g. NGN, USD. Each document keeps its own."
              )}
            </p>
          </div>
        </div>

        <Field
          icon={<Receipt size={16} />}
          label="Tax ID"
          value={form.taxId}
          onChange={(event) => set("taxId", event.target.value)}
          placeholder="TIN / VAT / GST number"
          maxLength={60}
          disabled={!editable}
        />
        {fields.taxId && <p className="-mt-2 text-xs text-red-300">{fields.taxId}</p>}

        {!editable && (
          <p className="text-xs text-slate-500">
            Your role can view these but not change them. An owner or
            administrator can.
          </p>
        )}

        <Notice kind="ok">{ok && "Business details saved."}</Notice>
        <Notice kind="err">{error}</Notice>

        {editable && (
          <Button type="submit" disabled={loading || unchanged}>
            {loading && <Loader2 size={16} className="animate-spin" />}
            Save changes
          </Button>
        )}
      </form>
    </Card>
  );
}


function ProfileCard() {
  const { user, updateProfile } = useAuth();
  const [name, setName] = useState(user?.name || "");
  const [loading, setLoading] = useState(false);
  const [ok, setOk] = useState(false);
  const [error, setError] = useState(null);

  async function onSave(e) {
    e.preventDefault();
    setLoading(true);
    setOk(false);
    setError(null);
    try {
      await updateProfile(name.trim());
      setOk(true);
    } catch (err) {
      setError(apiError(err, "Couldn't save your profile."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card icon={UserIcon} title="Profile" description="Your name and account email.">
      <form onSubmit={onSave} className="space-y-4">
        <Field
          icon={<UserIcon size={16} />}
          label="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Your name"
        />
        <Field icon={<Mail size={16} />} label="Email" value={user?.email || ""} disabled readOnly />
        <p className="-mt-2 text-xs text-slate-500">
          {user?.isGoogle ? "Signed in with Google." : null} Email can't be changed.
        </p>
        <Notice kind="ok">{ok && "Profile saved."}</Notice>
        <Notice kind="err">{error}</Notice>
        <Button type="submit" disabled={loading || name.trim() === (user?.name || "")}>
          {loading && <Loader2 size={16} className="animate-spin" />}
          Save changes
        </Button>
      </form>
    </Card>
  );
}

function PasswordCard({ hasPassword }) {
  const { changePassword } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [ok, setOk] = useState(false);
  const [error, setError] = useState(null);

  async function onSubmit(e) {
    e.preventDefault();
    setOk(false);
    setError(null);
    if (next.length < 8) return setError("New password must be at least 8 characters.");
    if (next !== confirm) return setError("Passwords don't match.");
    setLoading(true);
    try {
      await changePassword(current, next);
      setOk(true);
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch (err) {
      setError(apiError(err, "Couldn't update your password."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card
      icon={Lock}
      title={hasPassword ? "Password" : "Set a password"}
      description={
        hasPassword
          ? "Change the password you use to sign in."
          : "Your account uses Google sign-in. Set a password to also sign in with email."
      }
    >
      <form onSubmit={onSubmit} className="space-y-4">
        {hasPassword && (
          <Field
            icon={<Lock size={16} />}
            label="Current password"
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            placeholder="••••••••"
          />
        )}
        <Field
          icon={<Lock size={16} />}
          label="New password"
          type="password"
          autoComplete="new-password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          placeholder="At least 8 characters"
        />
        <Field
          icon={<Lock size={16} />}
          label="Confirm new password"
          type="password"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          placeholder="Re-enter new password"
        />
        <Notice kind="ok">{ok && "Password updated."}</Notice>
        <Notice kind="err">{error}</Notice>
        <Button type="submit" disabled={loading}>
          {loading && <Loader2 size={16} className="animate-spin" />}
          {hasPassword ? "Update password" : "Set password"}
        </Button>
      </form>
    </Card>
  );
}

function PlanCard() {
  const { user, plan, usage } = useAuth();
  return (
    <Card icon={CreditCard} title="Plan & usage" description="Your current subscription.">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="text-sm text-slate-300">
            Current plan: <span className="font-semibold capitalize text-white">{plan}</span>
          </div>
          {usage && (
            <div className="mt-1 text-xs text-slate-500">
              {usage.limit === null
                ? `${usage.used} invoices processed this month`
                : `${usage.used} / ${usage.limit} invoices used this month`}
              {user?.createdAt && ` · member since ${formatDate(user.createdAt)}`}
            </div>
          )}
        </div>
        <Button to="/dashboard/billing" variant="secondary" size="sm">
          Manage plan
        </Button>
      </div>
    </Card>
  );
}

function DangerZone() {
  const { user, deleteAccount } = useAuth();
  const navigate = useNavigate();
  const [confirm, setConfirm] = useState("");
  const [showConfirm, setShowConfirm] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const canDelete = confirm.trim().toLowerCase() === (user?.email || "").toLowerCase();

  async function onDelete() {
    if (!canDelete) return;
    setLoading(true);
    setError(null);
    try {
      await deleteAccount();
      navigate("/signup", { replace: true });
    } catch (err) {
      setError(apiError(err, "Couldn't delete your account."));
      setLoading(false);
      setShowConfirm(false);
    }
  }

  return (
    <section className="rounded-2xl border border-red-500/30 bg-red-500/[0.04] p-6">
      <div className="flex items-start gap-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-red-500/15 text-red-300">
          <ShieldAlert size={18} />
        </span>
        <div>
          <h2 className="text-base font-semibold text-white">Delete account</h2>
          <p className="mt-0.5 text-sm text-slate-400">
            Permanently delete your account and all data — extractions, uploaded files, API keys and
            webhooks. This cannot be undone.
          </p>
        </div>
      </div>

      <div className="mt-5 space-y-3">
        <label className="block">
          <span className="mb-1.5 block text-sm text-slate-300">
            Type your email <span className="font-mono text-slate-200">{user?.email}</span> to confirm
          </span>
          <input
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder={user?.email}
            className="h-11 w-full max-w-md rounded-xl border border-white/10 bg-ink-900/60 px-3.5 text-sm text-white placeholder:text-slate-600 outline-none focus:border-red-400/60 focus:ring-2 focus:ring-red-400/20"
          />
        </label>
        <Notice kind="err">{error}</Notice>
        <button
          onClick={() => setShowConfirm(true)}
          disabled={!canDelete || loading}
          className="inline-flex items-center gap-2 rounded-xl bg-red-500/90 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {loading && <Loader2 size={16} className="animate-spin" />}
          Delete my account
        </button>
      </div>

      <ConfirmDialog
        open={showConfirm}
        title="Delete your account?"
        description="This permanently deletes your account and all data — extractions, uploaded files, API keys and webhooks. This cannot be undone."
        confirmLabel="Delete account"
        loading={loading}
        onConfirm={onDelete}
        onClose={() => !loading && setShowConfirm(false)}
      />
    </section>
  );
}
