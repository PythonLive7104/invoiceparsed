import { useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { Loader2, Mail, Lock, User as UserIcon, AlertCircle, MailCheck } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { GoogleButton, googleEnabled } from "@/components/auth/GoogleButton";
import { useAuth, apiError } from "@/lib/auth.jsx";

export function AuthForm({ mode }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, register, resendVerification } = useAuth();
  const next = location.state?.from || "/dashboard";

  const isSignup = mode === "signup";
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  // Surface a failed Google redirect (?error=google) as a form error.
  const [error, setError] = useState(() =>
    new URLSearchParams(location.search).get("error") === "google"
      ? "Google sign-in failed. Please try again."
      : null
  );
  const [loading, setLoading] = useState(false);
  // Set after a successful signup → show the "confirm your email" panel.
  const [sentTo, setSentTo] = useState(null);
  const [resent, setResent] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (isSignup) {
        await register(name, email, password);
        setSentTo(email);
        setLoading(false);
        return;
      }
      await login(email, password);
      navigate(next, { replace: true });
    } catch (err) {
      setError(apiError(err, "Something went wrong."));
      setLoading(false);
    }
  }

  async function onResend() {
    try {
      await resendVerification(sentTo);
      setResent(true);
    } catch {
      /* keep the generic confirmation either way */
      setResent(true);
    }
  }

  if (sentTo) {
    return (
      <div className="w-full max-w-md">
        <div className="glass rounded-2xl p-8 text-center">
          <div className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-full bg-brand-500/15 text-brand-300">
            <MailCheck size={24} />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight text-white">Confirm your email</h1>
          <p className="mt-2 text-sm text-slate-400">
            We sent a confirmation link to <span className="text-slate-200">{sentTo}</span>. Click
            it to activate your account — you'll need to confirm before you can use InvoiceParsed.
          </p>
          <Button onClick={onResend} variant="secondary" className="mt-6 w-full" disabled={resent}>
            {resent ? "Email re-sent" : "Resend confirmation email"}
          </Button>
          <p className="mt-4 text-sm text-slate-400">
            <Link to="/login" className="font-medium text-brand-300 hover:text-brand-200">
              Back to sign in
            </Link>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-md">
      <div className="glass rounded-2xl p-8">
        <h1 className="text-2xl font-semibold tracking-tight text-white">
          {isSignup ? "Create your account" : "Welcome back"}
        </h1>
        <p className="mt-1.5 text-sm text-slate-400">
          {isSignup
            ? "Start extracting invoices in seconds. No card required."
            : "Sign in to your InvoiceParsed dashboard."}
        </p>

        {googleEnabled && (
          <div className="mt-7 space-y-4">
            <GoogleButton />
            <div className="flex items-center gap-3">
              <span className="h-px flex-1 bg-white/10" />
              <span className="text-xs text-slate-500">or continue with email</span>
              <span className="h-px flex-1 bg-white/10" />
            </div>
          </div>
        )}

        <form onSubmit={onSubmit} className={googleEnabled ? "mt-4 space-y-4" : "mt-7 space-y-4"}>
          {isSignup && (
            <Field
              icon={<UserIcon size={16} />}
              label="Name"
              type="text"
              autoComplete="name"
              placeholder="Sarah Designer"
              value={name}
              onChange={setName}
            />
          )}
          <Field
            icon={<Mail size={16} />}
            label="Email"
            type="email"
            autoComplete="email"
            placeholder="you@example.com"
            required
            value={email}
            onChange={setEmail}
          />
          <Field
            icon={<Lock size={16} />}
            label="Password"
            type="password"
            autoComplete={isSignup ? "new-password" : "current-password"}
            placeholder={isSignup ? "At least 8 characters" : "••••••••"}
            required
            value={password}
            onChange={setPassword}
          />

          {!isSignup && (
            <div className="-mt-1 text-right">
              <Link
                to="/forgot-password"
                className="text-xs font-medium text-brand-300 hover:text-brand-200"
              >
                Forgot password?
              </Link>
            </div>
          )}

          {error && (
            <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2.5 text-sm text-red-300">
              <AlertCircle size={16} className="mt-0.5 shrink-0" />
              {error}
            </div>
          )}

          <Button type="submit" className="w-full" disabled={loading}>
            {loading && <Loader2 size={16} className="animate-spin" />}
            {isSignup ? "Create account" : "Sign in"}
          </Button>
        </form>
      </div>

      <p className="mt-6 text-center text-sm text-slate-400">
        {isSignup ? "Already have an account? " : "New to InvoiceParsed? "}
        <Link
          to={isSignup ? "/login" : "/signup"}
          className="font-medium text-brand-300 hover:text-brand-200"
        >
          {isSignup ? "Sign in" : "Create one free"}
        </Link>
      </p>
    </div>
  );
}

function Field({ icon, label, value, onChange, ...rest }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-slate-300">{label}</span>
      <span className="relative block">
        <span className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500">
          {icon}
        </span>
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="h-11 w-full rounded-xl border border-white/10 bg-ink-900/60 pl-10 pr-3.5 text-sm text-white placeholder:text-slate-600 outline-none transition-colors focus:border-brand-400/60 focus:ring-2 focus:ring-brand-400/20"
          {...rest}
        />
      </span>
    </label>
  );
}
