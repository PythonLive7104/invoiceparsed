import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { useAuth } from "@/lib/auth.jsx";

/**
 * Landing page for the Google redirect flow. The backend bounces here with the
 * JWT in the URL fragment (#token=...). We adopt it, then route into the app.
 */
export default function GoogleCallback() {
  const { adoptToken } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    const token = new URLSearchParams(window.location.hash.slice(1)).get("token");
    if (!token) {
      navigate("/login?error=google", { replace: true });
      return;
    }
    adoptToken(token).then((ok) =>
      navigate(ok ? "/dashboard" : "/login?error=google", { replace: true })
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="grid min-h-screen place-items-center">
      <Loader2 className="animate-spin text-brand-400" size={28} />
    </div>
  );
}
