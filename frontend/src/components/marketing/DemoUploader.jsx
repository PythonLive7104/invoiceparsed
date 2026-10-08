import { lazy, Suspense, useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { AnimatePresence, motion } from "framer-motion";
import {
  UploadCloud,
  FileText,
  Receipt,
  Loader2,
  ScanLine,
  CheckCircle2,
  AlertCircle,
  RotateCcw,
  ArrowRight,
  Lock,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { api, apiError } from "@/lib/api";
import { saveClaimToken } from "@/lib/demo";
import { track, EVENTS } from "@/lib/analytics";
import { cn, formatBytes } from "@/lib/utils";

// Only needed once an extraction finishes, so it gets its own chunk again.
const ResultCard = lazy(() =>
  import("@/components/dashboard/ResultCard").then((m) => ({ default: m.ResultCard })),
);

const ACCEPT = {
  "application/pdf": [".pdf"],
  "image/jpeg": [".jpg", ".jpeg"],
  "image/png": [".png"],
};
const MAX = 10 * 1024 * 1024;

const DOC_TYPES = [
  { id: "invoice", label: "Invoice", icon: FileText },
  { id: "receipt", label: "Receipt", icon: Receipt },
];

/**
 * The interactive half of the landing-page demo (see TryItFree, which owns the
 * section chrome and lazy-loads this).
 */
export function DemoUploader({ initialDemo }) {
  // TryItFree has already fetched this; it only changes after an extraction.
  const [demo, setDemo] = useState(initialDemo);
  const [status, setStatus] = useState("idle"); // idle|selected|processing|done|error
  const [docType, setDocType] = useState("invoice");
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [limitHit, setLimitHit] = useState(initialDemo?.remaining === 0);
  const [uploadPct, setUploadPct] = useState(0);

  const onDrop = useCallback((accepted, rejected) => {
    setError(null);
    if (rejected.length) {
      setError("Unsupported file. Upload a PDF, JPG or PNG up to 10MB.");
      return;
    }
    if (!accepted.length) return;
    setFile(accepted[0]);
    setStatus("selected");
  }, []);

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop,
    accept: ACCEPT,
    maxSize: MAX,
    multiple: false,
    noClick: true,
    noKeyboard: true,
    disabled: limitHit || status === "processing",
  });

  function reset() {
    setFile(null);
    setResult(null);
    setError(null);
    setUploadPct(0);
    setStatus("idle");
  }

  async function extract() {
    if (!file) return;
    setStatus("processing");
    setError(null);
    setUploadPct(0);
    track(EVENTS.DEMO_STARTED, { docType });
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("doc_type", docType);
      const { data } = await api.post("/api/demo/extract", fd, {
        onUploadProgress: (e) => {
          if (e.total) setUploadPct(Math.round((e.loaded / e.total) * 100));
        },
      });
      // Hold the token so creating an account adopts this extraction.
      saveClaimToken(data.claimToken);
      setResult({ docType: data.docType, fileName: data.fileName, invoice: data.invoice });
      setDemo(data.demo);
      setStatus("done");
      track(EVENTS.DEMO_COMPLETED, { docType: data.docType });
    } catch (err) {
      const code = err?.response?.data?.code;
      if (err?.response?.data?.demo) setDemo(err.response.data.demo);
      if (code === "DEMO_LIMIT_REACHED") setLimitHit(true);
      setError(apiError(err, "Extraction failed. Please try another file."));
      setStatus("error");
      track(EVENTS.DEMO_FAILED, { docType, code: code || "unknown" });
    }
  }

  const docLabel = docType === "receipt" ? "receipt" : "invoice";

  return (
    <AnimatePresence mode="wait">
      {status === "done" && result ? (
        <motion.div
          key="result"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-4"
        >
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-emerald-500/25 bg-emerald-500/[0.07] px-4 py-3">
            <div className="flex items-center gap-2.5 text-sm text-emerald-200">
              <CheckCircle2 size={18} /> Extracted in seconds — this is the real output.
            </div>
            <button
              onClick={reset}
              className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-300 transition-colors hover:text-white"
            >
              <RotateCcw size={13} /> Start over
            </button>
          </div>

          <Suspense
            fallback={
              <div className="flex min-h-[200px] items-center justify-center rounded-2xl border border-white/10 bg-white/[0.02]">
                <Loader2 size={22} className="animate-spin text-brand-400" />
              </div>
            }
          >
            <ResultCard
              docType={result.docType}
              invoice={result.invoice}
              fileName={result.fileName}
              locked
              onLockedAction={() => track(EVENTS.DEMO_EXPORT_BLOCKED, { docType: result.docType })}
            />
          </Suspense>

          <SignupGate docType={result.docType} />
        </motion.div>
      ) : status === "processing" ? (
        <Processing key="processing" file={file} uploadPct={uploadPct} docLabel={docLabel} />
      ) : (
        <motion.div key="upload" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
          {limitHit ? (
            <LimitPanel />
          ) : (
            <>
              <div className="mb-5 flex justify-center">
                <div className="inline-flex rounded-full border border-white/10 bg-white/[0.03] p-1">
                  {DOC_TYPES.map((t) => (
                    <button
                      key={t.id}
                      onClick={() => setDocType(t.id)}
                      className={cn(
                        "inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition-all",
                        docType === t.id
                          ? "bg-brand-gradient text-white shadow-glow-sm"
                          : "text-slate-400 hover:text-white",
                      )}
                    >
                      <t.icon size={15} /> {t.label}
                    </button>
                  ))}
                </div>
              </div>

              <div
                {...getRootProps()}
                className={cn(
                  "relative flex min-h-[300px] flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-all",
                  isDragActive
                    ? "border-brand-400/70 bg-brand-500/[0.08]"
                    : "border-white/12 bg-white/[0.015] hover:border-white/20",
                )}
              >
                <input {...getInputProps()} />

                {status === "selected" && file ? (
                  <div className="w-full max-w-md">
                    <div className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 text-left">
                      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-brand-500/15 text-brand-300">
                        <FileText size={17} />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium text-white">{file.name}</div>
                        <div className="text-xs text-slate-500">{formatBytes(file.size)}</div>
                      </div>
                      <button
                        onClick={reset}
                        aria-label="Remove file"
                        className="shrink-0 rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-white/[0.06] hover:text-white"
                      >
                        <X size={16} />
                      </button>
                    </div>
                    <div className="mt-5 flex flex-col items-center gap-3 sm:flex-row sm:justify-center">
                      <Button onClick={extract} size="lg">
                        <ScanLine size={18} /> Extract this {docLabel}
                      </Button>
                      <button
                        onClick={open}
                        className="text-sm text-slate-400 transition-colors hover:text-white"
                      >
                        choose a different file
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="relative mb-5">
                      <span className="absolute inset-0 animate-pulse-ring rounded-2xl bg-brand-500/30" />
                      <span className="relative grid h-16 w-16 place-items-center rounded-2xl bg-brand-gradient text-white shadow-glow-sm">
                        <UploadCloud size={28} />
                      </span>
                    </div>
                    <h3 className="text-xl font-semibold text-white">
                      {isDragActive
                        ? `Drop your ${docLabel} here`
                        : `Drag & drop ${docType === "receipt" ? "a receipt" : "an invoice"}`}
                    </h3>
                    <p className="mt-2 text-sm text-slate-400">PDF, JPG or PNG · up to 10MB</p>
                    <Button onClick={open} variant="secondary" className="mt-6">
                      Choose a file
                    </Button>
                    <p className="mt-5 text-xs text-slate-500">
                      Your file is used for this extraction and deleted within 24 hours.
                    </p>
                  </>
                )}
              </div>
            </>
          )}

          {error && (
            <div className="mt-4 flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
              <AlertCircle size={16} className="mt-0.5 shrink-0" />
              {error}
            </div>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/** Shown under a finished demo result — the actual ask. */
function SignupGate({ docType }) {
  return (
    <div className="glass gradient-border rounded-2xl p-6 text-center sm:p-8">
      <div className="mx-auto grid h-11 w-11 place-items-center rounded-xl bg-brand-500/15 text-brand-300 ring-1 ring-inset ring-brand-400/20">
        <Lock size={20} />
      </div>
      <h3 className="mt-4 text-xl font-semibold text-white">Want this as a spreadsheet?</h3>
      <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-slate-400">
        Create a free account to export this {docType === "receipt" ? "receipt" : "invoice"} as
        Excel, CSV or JSON, correct any field and keep it in your history.{" "}
        <span className="text-slate-300">
          This extraction is saved to your account automatically — you won't need to upload it
          again.
        </span>
      </p>
      <div className="mt-6 flex flex-col items-center justify-center gap-3 sm:flex-row">
        <Button
          to="/signup"
          size="lg"
          onClick={() => track(EVENTS.DEMO_EXPORT_BLOCKED, { docType, from: "gate" })}
        >
          Create free account <ArrowRight size={18} />
        </Button>
        <span className="text-xs text-slate-500">
          5 more documents a month, free. No card required.
        </span>
      </div>
    </div>
  );
}

/** Shown when this visitor has already used their free extraction. */
function LimitPanel() {
  return (
    <div className="glass gradient-border rounded-2xl p-8 text-center sm:p-10">
      <div className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-brand-500/15 text-brand-300 ring-1 ring-inset ring-brand-400/20">
        <CheckCircle2 size={22} />
      </div>
      <h3 className="mt-5 text-2xl font-semibold text-white">You've used your free demo</h3>
      <p className="mx-auto mt-3 max-w-md text-slate-400">
        Create a free account to keep going — 5 documents every month, Excel/CSV/JSON export and
        your full history. No card required.
      </p>
      <div className="mt-7 flex flex-col items-center justify-center gap-3 sm:flex-row">
        <Button
          to="/signup"
          size="lg"
          onClick={() => track(EVENTS.DEMO_EXPORT_BLOCKED, { from: "limit" })}
        >
          Create free account <ArrowRight size={18} />
        </Button>
        <Button to="/login" variant="ghost">
          or sign in
        </Button>
      </div>
    </div>
  );
}

function Processing({ file, uploadPct, docLabel }) {
  const uploading = uploadPct < 100;
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex min-h-[300px] flex-col items-center justify-center rounded-2xl border border-white/10 bg-white/[0.02] px-6 py-12 text-center"
    >
      <div className="relative mb-6">
        <span className="absolute inset-0 animate-pulse-ring rounded-2xl bg-brand-500/30" />
        <span className="relative grid h-16 w-16 place-items-center rounded-2xl bg-brand-gradient text-white shadow-glow-sm">
          <ScanLine size={28} />
        </span>
      </div>
      <h3 className="text-xl font-semibold text-white">
        {uploading ? `Uploading your ${docLabel}…` : `Reading your ${docLabel}…`}
      </h3>
      <p className="mt-2 max-w-sm text-sm text-slate-400">
        {uploading
          ? file?.name
          : "Finding the vendor, dates, line items and totals. This usually takes a few seconds."}
      </p>

      <div className="mt-6 h-1.5 w-full max-w-xs overflow-hidden rounded-full bg-white/[0.08]">
        {uploading ? (
          <div
            className="h-full rounded-full bg-brand-gradient transition-all duration-200"
            style={{ width: `${uploadPct}%` }}
          />
        ) : (
          <div className="h-full w-1/3 animate-indeterminate rounded-full bg-brand-gradient" />
        )}
      </div>

      <div className="mt-5 flex items-center gap-2 text-xs text-slate-500">
        <Loader2 size={13} className="animate-spin" /> Don't close this tab
      </div>
    </motion.div>
  );
}
