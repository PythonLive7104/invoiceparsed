import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { Sparkles, UploadCloud } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/lib/auth.jsx";
import { api } from "@/lib/api";

// The interactive uploader pulls in react-dropzone and the result cards. The
// landing page is loaded eagerly for LCP, so the heavy part is split out and
// fetched when the section scrolls into view (or on first interaction) — the
// static shell below is pixel-compatible with it, so nothing shifts.
const DemoUploader = lazy(() =>
  import("@/components/marketing/DemoUploader").then((m) => ({ default: m.DemoUploader })),
);

/**
 * Try-before-signup. The single highest-leverage thing on this page: a visitor
 * can run a real extraction here without an account. Exporting the result is
 * what asks for the account, and the extraction is held server-side so signing
 * up adopts it instead of making them upload again.
 */
export function TryItFree() {
  const { user } = useAuth();
  const [active, setActive] = useState(false);
  const [demo, setDemo] = useState(null); // {enabled, remaining, limit} | null
  const ref = useRef(null);

  // Warm the chunk as soon as the section is anywhere near the viewport.
  useEffect(() => {
    const el = ref.current;
    if (!el || active) return;
    if (typeof IntersectionObserver === "undefined") {
      setActive(true);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setActive(true);
          io.disconnect();
        }
      },
      { rootMargin: "400px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [active]);

  // Signed-in visitors have the real thing in their dashboard — don't offer them
  // a one-shot anonymous demo.
  if (user) return null;

  // Asked for once the section is in play, so it stays off the critical path.
  // A failure is non-fatal: assume available and let the POST report the truth.
  useEffect(() => {
    if (!active || demo || user) return;
    let cancelled = false;
    api
      .get("/api/demo/status")
      .then(({ data }) => !cancelled && setDemo(data))
      .catch(() => !cancelled && setDemo({ enabled: true, remaining: 1, limit: 1 }));
    return () => {
      cancelled = true;
    };
  }, [active, demo, user]);

  // Server says the demo is off (or has no model key) — drop the whole section
  // rather than leaving a heading above an empty box.
  if (demo && demo.enabled === false) return null;

  return (
    <section id="try" className="relative scroll-mt-24 py-16 sm:py-20">
      <div className="container-page">
        <div className="mx-auto max-w-2xl text-center">
          <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-xs font-medium text-accent-cyan">
            <Sparkles size={14} /> No account needed
          </span>
          <h2 className="mt-4 text-balance text-4xl font-semibold tracking-tight text-white sm:text-5xl">
            Try it on a real invoice
          </h2>
          <p className="mt-4 text-lg text-slate-400">
            Drop in an invoice or receipt and watch it come back as clean, structured data. One
            free extraction — no signup, no card.
          </p>
        </div>

        <div ref={ref} className="mx-auto mt-10 max-w-4xl">
          {active && demo ? (
            <Suspense fallback={<UploadShell />}>
              <DemoUploader initialDemo={demo} />
            </Suspense>
          ) : (
            <UploadShell onInteract={() => setActive(true)} />
          )}
        </div>
      </div>
    </section>
  );
}

/**
 * Static stand-in for the uploader: same dimensions and visuals, no heavy deps.
 * Any interaction with it pulls the real widget in immediately.
 */
function UploadShell({ onInteract }) {
  return (
    <>
      <div className="mb-5 flex justify-center">
        <div className="inline-flex rounded-full border border-white/10 bg-white/[0.03] p-1">
          <span className="inline-flex items-center gap-2 rounded-full bg-brand-gradient px-4 py-2 text-sm font-medium text-white shadow-glow-sm">
            Invoice
          </span>
          <span className="inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium text-slate-400">
            Receipt
          </span>
        </div>
      </div>
      <div
        onMouseEnter={onInteract}
        onDragEnter={onInteract}
        className="relative flex min-h-[300px] flex-col items-center justify-center rounded-2xl border-2 border-dashed border-white/12 bg-white/[0.015] px-6 py-10 text-center"
      >
        <div className="relative mb-5">
          <span className="absolute inset-0 animate-pulse-ring rounded-2xl bg-brand-500/30" />
          <span className="relative grid h-16 w-16 place-items-center rounded-2xl bg-brand-gradient text-white shadow-glow-sm">
            <UploadCloud size={28} />
          </span>
        </div>
        <h3 className="text-xl font-semibold text-white">Drag &amp; drop an invoice</h3>
        <p className="mt-2 text-sm text-slate-400">PDF, JPG or PNG · up to 10MB</p>
        <Button onClick={onInteract} variant="secondary" className="mt-6">
          Choose a file
        </Button>
        <p className="mt-5 text-xs text-slate-500">
          Your file is used for this extraction and deleted within 24 hours.
        </p>
      </div>
    </>
  );
}
