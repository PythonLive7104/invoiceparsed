import { useEffect, useRef } from "react";

const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;
const API_URL = import.meta.env.VITE_API_URL || "http://localhost:5000";

/** Whether Google sign-in is configured (controls divider/visibility). */
export const googleEnabled = Boolean(CLIENT_ID);

let scriptPromise;
function loadGis() {
  if (!scriptPromise) {
    scriptPromise = new Promise((resolve, reject) => {
      if (window.google?.accounts?.id) return resolve();
      const s = document.createElement("script");
      s.src = "https://accounts.google.com/gsi/client";
      s.async = true;
      s.defer = true;
      s.onload = resolve;
      s.onerror = reject;
      document.head.appendChild(s);
    });
  }
  return scriptPromise;
}

/**
 * Renders Google's official "Continue with Google" button. Uses the full-page
 * redirect flow (ux_mode "redirect"): instead of a popup, the browser navigates
 * to Google and the signed ID token is POSTed to the backend `login_uri`, which
 * redirects back to the SPA with a session token. Renders nothing if no client
 * ID is configured (VITE_GOOGLE_CLIENT_ID).
 */
export function GoogleButton() {
  const ref = useRef(null);

  useEffect(() => {
    if (!CLIENT_ID) return;
    let cancelled = false;
    loadGis()
      .then(() => {
        if (cancelled || !window.google || !ref.current) return;
        window.google.accounts.id.initialize({
          client_id: CLIENT_ID,
          ux_mode: "redirect",
          login_uri: `${API_URL}/api/auth/google/callback`,
        });
        window.google.accounts.id.renderButton(ref.current, {
          theme: "filled_black",
          size: "large",
          shape: "pill",
          text: "continue_with",
          width: 360,
        });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!CLIENT_ID) return null;
  return <div ref={ref} className="flex min-h-[44px] justify-center [color-scheme:light]" />;
}
