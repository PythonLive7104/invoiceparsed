import { useState } from "react";
import { Link } from "react-router-dom";
import { Loader2, Mail, MailCheck, ArrowLeft } from "lucide-react";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { Button } from "@/components/ui/Button";
import { useAuth, apiError } from "@/lib/auth.jsx";

export default function ForgotPassword() {
  const { forgotPassword } = useAuth();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function onSubmit(e) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await forgotPassword(email);
      setSent(true);
    } catch (err) {
      setError(apiError(err, "Couldn't send the reset email."));
    }
    setLoading(false);
  }

  return (
    <AuthLayout>
      <div className="w-full max-w-md">
        <div className="glass rounded-2xl p-8">
          {sent ? (
            <div className="text-center">
              <span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-emerald-500/15 text-emerald-300">
                <MailCheck size={22} />
              </span>
              <h1 className="mt-4 text-2xl font-semibold tracking-tight text-white">Check your inbox</h1>
              <p className="mt-2 text-sm text-slate-400">
                If an account exists for <span className="text-slate-200">{email}</span>, we've sent a
                link to reset your password. It expires in 1 hour.
              </p>
            </div>
          ) : (
            <>
              <h1 className="text-2xl font-semibold tracking-tight text-white">Reset your password</h1>
              <p className="mt-1.5 text-sm text-slate-400">
                Enter your email and we'll send you a reset link.
              </p>

              <form onSubmit={onSubmit} className="mt-7 space-y-4">
                <label className="block">
                  <span className="mb-1.5 block text-sm font-medium text-slate-300">Email</span>
                  <span className="relative block">
                    <span className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500">
                      <Mail size={16} />
                    </span>
                    <input
                      type="email"
                      required
                      autoComplete="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="you@example.com"
                      className="h-11 w-full rounded-xl border border-white/10 bg-ink-900/60 pl-10 pr-3.5 text-sm text-white placeholder:text-slate-600 outline-none transition-colors focus:border-brand-400/60 focus:ring-2 focus:ring-brand-400/20"
                    />
                  </span>
                </label>

                {error && <p className="text-sm text-red-300">{error}</p>}

                <Button type="submit" className="w-full" disabled={loading}>
                  {loading && <Loader2 size={16} className="animate-spin" />}
                  Send reset link
                </Button>
              </form>
            </>
          )}
        </div>

        <p className="mt-6 text-center text-sm text-slate-400">
          <Link to="/login" className="inline-flex items-center gap-1.5 font-medium text-brand-300 hover:text-brand-200">
            <ArrowLeft size={14} /> Back to sign in
          </Link>
        </p>
      </div>
    </AuthLayout>
  );
}
