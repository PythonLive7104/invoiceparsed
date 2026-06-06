import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Loader2, AlertCircle, MailCheck } from "lucide-react";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { useAuth, apiError } from "@/lib/auth.jsx";

/**
 * Landing page for the email-confirmation link (/verify-email?token=...). It
 * exchanges the token for a session and drops the user into the dashboard, or
 * shows an error if the link is invalid/expired.
 */
export default function VerifyEmail() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const navigate = useNavigate();
  const { verifyEmail } = useAuth();
  const [error, setError] = useState(token ? null : "This confirmation link is missing its token.");
  const ran = useRef(false);

  useEffect(() => {
    if (!token || ran.current) return;
    ran.current = true; // guard React 18 StrictMode double-invoke
    verifyEmail(token)
      .then(() => navigate("/dashboard", { replace: true }))
      .catch((err) => setError(apiError(err, "This confirmation link is invalid or has expired.")));
  }, [token, verifyEmail, navigate]);

  return (
    <AuthLayout>
      <div className="w-full max-w-md">
        <div className="glass rounded-2xl p-8 text-center">
          {error ? (
            <>
              <div className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-full bg-red-500/15 text-red-300">
                <AlertCircle size={24} />
              </div>
              <h1 className="text-2xl font-semibold tracking-tight text-white">Confirmation failed</h1>
              <p className="mt-2 text-sm text-slate-400">{error}</p>
              <p className="mt-6 text-sm text-slate-400">
                <Link to="/login" className="font-medium text-brand-300 hover:text-brand-200">
                  Back to sign in
                </Link>
              </p>
            </>
          ) : (
            <>
              <div className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-full bg-brand-500/15 text-brand-300">
                <MailCheck size={24} />
              </div>
              <h1 className="text-2xl font-semibold tracking-tight text-white">Confirming your email…</h1>
              <p className="mt-2 flex items-center justify-center gap-2 text-sm text-slate-400">
                <Loader2 className="animate-spin" size={16} /> Just a moment.
              </p>
            </>
          )}
        </div>
      </div>
    </AuthLayout>
  );
}
