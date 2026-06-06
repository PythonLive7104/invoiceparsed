import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Loader2, Lock, AlertCircle } from "lucide-react";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { Button } from "@/components/ui/Button";
import { useAuth, apiError } from "@/lib/auth.jsx";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const navigate = useNavigate();
  const { resetPassword } = useAuth();

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function onSubmit(e) {
    e.preventDefault();
    setError(null);
    if (password.length < 8) return setError("Password must be at least 8 characters.");
    if (password !== confirm) return setError("Passwords don't match.");
    setLoading(true);
    try {
      await resetPassword(token, password);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(apiError(err, "Couldn't reset your password."));
      setLoading(false);
    }
  }

  return (
    <AuthLayout>
      <div className="w-full max-w-md">
        <div className="glass rounded-2xl p-8">
          <h1 className="text-2xl font-semibold tracking-tight text-white">Choose a new password</h1>
          <p className="mt-1.5 text-sm text-slate-400">
            {token ? "Enter a new password for your account." : "This reset link is missing its token."}
          </p>

          {!token ? (
            <p className="mt-5 flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2.5 text-sm text-red-300">
              <AlertCircle size={16} /> Invalid reset link. Request a new one.
            </p>
          ) : (
            <form onSubmit={onSubmit} className="mt-7 space-y-4">
              <PasswordField label="New password" value={password} onChange={setPassword} autoComplete="new-password" />
              <PasswordField label="Confirm password" value={confirm} onChange={setConfirm} autoComplete="new-password" />

              {error && (
                <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2.5 text-sm text-red-300">
                  <AlertCircle size={16} className="mt-0.5 shrink-0" />
                  {error}
                </div>
              )}

              <Button type="submit" className="w-full" disabled={loading}>
                {loading && <Loader2 size={16} className="animate-spin" />}
                Reset password & sign in
              </Button>
            </form>
          )}
        </div>

        <p className="mt-6 text-center text-sm text-slate-400">
          <Link to="/login" className="font-medium text-brand-300 hover:text-brand-200">
            Back to sign in
          </Link>
        </p>
      </div>
    </AuthLayout>
  );
}

function PasswordField({ label, value, onChange, autoComplete }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-slate-300">{label}</span>
      <span className="relative block">
        <span className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500">
          <Lock size={16} />
        </span>
        <input
          type="password"
          required
          autoComplete={autoComplete}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="••••••••"
          className="h-11 w-full rounded-xl border border-white/10 bg-ink-900/60 pl-10 pr-3.5 text-sm text-white placeholder:text-slate-600 outline-none transition-colors focus:border-brand-400/60 focus:ring-2 focus:ring-brand-400/20"
        />
      </span>
    </label>
  );
}
