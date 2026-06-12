import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { HelmetProvider } from "react-helmet-async";
import * as Sentry from "@sentry/react";
import { AuthProvider } from "@/lib/auth.jsx";
import App from "./App.jsx";
import "./index.css";

// Error monitoring — only active when a DSN is provided at build time.
if (import.meta.env.VITE_SENTRY_DSN) {
  Sentry.init({
    dsn: import.meta.env.VITE_SENTRY_DSN,
    environment: import.meta.env.VITE_SENTRY_ENVIRONMENT || "production",
    integrations: [Sentry.browserTracingIntegration()],
    tracesSampleRate: Number(import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE || 0),
    sendDefaultPii: false,
  });
}

function Fallback({ error }) {
  const detail =
    (error && (error.message || String(error))) || "Unknown error";
  return (
    <div className="grid min-h-screen place-items-center bg-ink-950 px-6 text-center">
      <div className="max-w-lg">
        <h1 className="text-xl font-semibold text-white">Something went wrong</h1>
        <p className="mt-2 text-sm text-slate-400">
          The error has been reported. Please refresh the page.
        </p>
        {/* Surface the underlying message so issues can be diagnosed in the
            field (e.g. on mobile, with no dev console available). */}
        <pre className="mt-4 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-xl border border-white/10 bg-white/[0.03] p-3 text-left text-xs text-amber-300">
          {detail}
        </pre>
        <button
          onClick={() => window.location.reload()}
          className="mt-6 rounded-xl bg-brand-gradient px-5 py-2.5 text-sm font-medium text-white"
        >
          Reload
        </button>
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <Sentry.ErrorBoundary fallback={({ error }) => <Fallback error={error} />}>
      <HelmetProvider>
        <BrowserRouter>
          <AuthProvider>
            <App />
          </AuthProvider>
        </BrowserRouter>
      </HelmetProvider>
    </Sentry.ErrorBoundary>
  </React.StrictMode>,
);
