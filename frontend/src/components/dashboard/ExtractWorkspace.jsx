import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useDropzone } from "react-dropzone";
import { AnimatePresence, motion } from "framer-motion";
import {
  UploadCloud,
  FileText,
  Image as ImageIcon,
  Loader2,
  ScanLine,
  Sparkles,
  CheckCircle2,
  AlertCircle,
  RotateCcw,
  X,
  Layers,
  Files,
  Lock,
  MinusCircle,
  Receipt,
  Landmark,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { ResultCard } from "@/components/dashboard/ResultCard";
import { cn, formatBytes } from "@/lib/utils";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/lib/auth.jsx";
import { planAllows } from "@/lib/plans";

const ACCEPT = {
  "application/pdf": [".pdf"],
  "image/jpeg": [".jpg", ".jpeg"],
  "image/png": [".png"],
};
const MAX = 10 * 1024 * 1024;
const MAX_FILES = 15;

export function ExtractWorkspace() {
  const { user, usage, refreshUsage, setUsage } = useAuth();
  const canBatch = planAllows(user?.plan, "batch");
  const canMultiPage = planAllows(user?.plan, "multiPage");
  const canMulti = canBatch || canMultiPage;
  const canStatements = planAllows(user?.plan, "statements");

  const [status, setStatus] = useState("idle"); // idle|selected|processing|done|error
  const [files, setFiles] = useState([]);
  const [docType, setDocType] = useState("invoice"); // invoice|receipt
  const [mode, setMode] = useState("single"); // single|batch|combine
  const [result, setResult] = useState(null); // single/combine result
  const [batchItems, setBatchItems] = useState([]); // batch results
  const [error, setError] = useState(null);
  const [uploadPct, setUploadPct] = useState(0); // single/combine upload progress

  const atLimit = usage?.atLimit;
  const docLabel = { receipt: "receipt", statement: "bank statement" }[docType] || "invoice";
  const docArticle = docType === "invoice" ? "an" : "a";
  // Bank statements are a Business-only feature. Block upload when selected without it.
  const statementLocked = docType === "statement" && !canStatements;
  // Statements have their own monthly allowance (e.g. 300 on Business).
  const stmt = usage?.statements;
  const statementSelected = docType === "statement" && canStatements;
  const statementAtLimit = statementSelected && stmt?.allowed && stmt?.atLimit;
  const blocked = atLimit || statementLocked || statementAtLimit;

  const onDrop = useCallback(
    (accepted, rejected) => {
      setError(null);
      if (rejected.length) {
        setError("Unsupported file. Upload PDF, JPG or PNG up to 10MB each.");
      }
      if (!accepted.length) return;
      setFiles((prev) => {
        const merged = [...prev];
        for (const f of accepted) {
          if (!merged.some((m) => m.name === f.name && m.size === f.size)) merged.push(f);
        }
        return merged.slice(0, MAX_FILES);
      });
      setStatus("selected");
    },
    [],
  );

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop,
    accept: ACCEPT,
    maxSize: MAX,
    multiple: canMulti,
    maxFiles: canMulti ? MAX_FILES : 1,
    noClick: true,
    noKeyboard: true,
    disabled: blocked || status === "processing",
  });

  function removeFile(idx) {
    setFiles((prev) => {
      const next = prev.filter((_, i) => i !== idx);
      if (next.length === 0) setStatus("idle");
      return next;
    });
  }

  function reset() {
    setFiles([]);
    setResult(null);
    setBatchItems([]);
    setError(null);
    setMode("single");
    setStatus("idle");
  }

  // Single file, or several files combined into ONE multi-page invoice.
  async function extractCombined(isCombine) {
    setMode(isCombine ? "combine" : "single");
    setStatus("processing");
    setError(null);
    setUploadPct(0);
    try {
      const fd = new FormData();
      (isCombine ? files : [files[0]]).forEach((f) => fd.append("file", f));
      fd.append("doc_type", docType);
      const { data } = await api.post("/api/extract", fd, {
        onUploadProgress: (e) => {
          if (e.total) setUploadPct(Math.round((e.loaded / e.total) * 100));
        },
      });
      setResult({ id: data.id, fileName: data.fileName, invoice: data.invoice, docType: data.docType });
      setUsage(data.usage);
      setStatus("done");
    } catch (err) {
      if (err?.response?.data?.usage) setUsage(err.response.data.usage);
      setError(apiError(err, "Extraction failed."));
      setStatus("error");
    } finally {
      refreshUsage();
    }
  }

  // Each file → its own invoice, processed sequentially.
  async function extractBatch() {
    setMode("batch");
    setStatus("processing");
    setBatchItems(files.map((f) => ({ name: f.name, status: "pending" })));
    for (let i = 0; i < files.length; i++) {
      setBatchItems((prev) => prev.map((it, idx) => (idx === i ? { ...it, status: "processing", pct: 0 } : it)));
      try {
        const fd = new FormData();
        fd.append("file", files[i]);
        fd.append("mode", "batch");
        fd.append("doc_type", docType);
        const { data } = await api.post("/api/extract", fd, {
          onUploadProgress: (e) => {
            if (!e.total) return;
            const pct = Math.round((e.loaded / e.total) * 100);
            setBatchItems((prev) => prev.map((it, idx) => (idx === i ? { ...it, pct } : it)));
          },
        });
        setUsage(data.usage);
        setBatchItems((prev) => prev.map((it, idx) => (idx === i ? { ...it, status: "done", result: data } : it)));
      } catch (err) {
        if (err?.response?.data?.usage) setUsage(err.response.data.usage);
        const code = err?.response?.data?.code;
        setBatchItems((prev) => prev.map((it, idx) => (idx === i ? { ...it, status: "error", error: apiError(err) } : it)));
        if (code === "LIMIT_REACHED") {
          setBatchItems((prev) => prev.map((it, idx) => (idx > i ? { ...it, status: "skipped" } : it)));
          break;
        }
      }
    }
    setStatus("done");
    refreshUsage();
  }

  return (
    <div className="space-y-6">
      {atLimit && status !== "done" && <LimitBanner usage={usage} />}

      {(status === "idle" || status === "selected") && (
        <DocTypeToggle value={docType} onChange={setDocType} disabled={atLimit} canStatements={canStatements} />
      )}

      {statementLocked && status !== "done" && <StatementLockBanner />}

      {statementSelected && stmt?.limit != null && status !== "done" && (
        statementAtLimit ? <StatementLimitBanner stmt={stmt} /> : <StatementAllowanceNote stmt={stmt} />
      )}

      <AnimatePresence mode="wait">
        {status === "done" ? (
          <motion.div key="result" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
            {mode === "batch" ? (
              <BatchResults items={batchItems} onReset={reset} />
            ) : (
              <>
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-emerald-500/25 bg-emerald-500/[0.07] px-4 py-3">
                  <div className="flex items-center gap-2.5 text-sm text-emerald-200">
                    <CheckCircle2 size={18} />
                    {mode === "combine"
                      ? "Pages combined into one invoice"
                      : "Extraction complete"}
                    {" — "}
                    {result?.docType === "statement" && stmt?.allowed && stmt?.limit != null
                      ? `${stmt.remaining} of ${stmt.limit} bank statements left this month`
                      : usage?.limit === null
                        ? `${usage?.used} processed this month`
                        : `${usage?.remaining} of ${usage?.limit} documents left this month`}
                  </div>
                  <Button size="sm" variant="secondary" onClick={reset}>
                    <RotateCcw size={14} /> Extract another
                  </Button>
                </div>
                {result && (
                  <ResultCard docType={result.docType} invoice={result.invoice} extractionId={result.id} fileName={result.fileName} />
                )}
              </>
            )}
          </motion.div>
        ) : status === "processing" ? (
          mode === "batch" ? (
            <BatchProgress key="batchproc" items={batchItems} />
          ) : (
            <ProcessingState key="processing" files={files} combine={mode === "combine"} uploadPct={uploadPct} docLabel={docLabel} />
          )
        ) : (
          <motion.div key="upload" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            <div
              {...getRootProps()}
              className={cn(
                "relative flex min-h-[340px] flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-all",
                blocked ? "cursor-not-allowed border-white/10 opacity-50" : "cursor-default",
                isDragActive ? "border-brand-400/70 bg-brand-500/[0.08]" : "border-white/12 bg-white/[0.015] hover:border-white/20",
              )}
            >
              <input {...getInputProps()} />

              {status === "selected" && files.length > 0 ? (
                <SelectedFiles
                  files={files}
                  canBatch={canBatch}
                  canMultiPage={canMultiPage}
                  docLabel={docLabel}
                  disabled={blocked}
                  onRemove={removeFile}
                  onAddMore={open}
                  onSingle={() => extractCombined(false)}
                  onBatch={extractBatch}
                  onCombine={() => extractCombined(true)}
                  onClear={reset}
                />
              ) : (
                <>
                  <div className="relative mb-5">
                    <span className="absolute inset-0 animate-pulse-ring rounded-2xl bg-brand-500/30" />
                    <span className="relative grid h-16 w-16 place-items-center rounded-2xl bg-brand-gradient text-white shadow-glow-sm">
                      <UploadCloud size={28} />
                    </span>
                  </div>
                  <h3 className="text-xl font-semibold text-white">
                    {isDragActive ? `Drop your ${docLabel} here` : `Upload ${docArticle} ${docLabel}`}
                  </h3>
                  <p className="mt-2 max-w-sm text-sm text-slate-400">
                    {canMulti
                      ? "Drag & drop one or more PDFs or images, or browse. Up to 10MB each."
                      : "Drag & drop a PDF or image, or browse to select. Up to 10MB."}
                  </p>
                  <Button className="mt-6" onClick={open} disabled={blocked} type="button">
                    <UploadCloud size={16} /> Choose file{canMulti ? "s" : ""}
                  </Button>
                  <div className="mt-5 flex items-center gap-3 text-xs text-slate-500">
                    <span className="rounded-md bg-white/[0.05] px-2 py-1">PDF</span>
                    <span className="rounded-md bg-white/[0.05] px-2 py-1">JPG</span>
                    <span className="rounded-md bg-white/[0.05] px-2 py-1">PNG</span>
                  </div>

                  {!canMulti && (
                    <p className="mt-5 flex items-center gap-1.5 text-xs text-slate-500">
                      <Lock size={12} />
                      Batch upload & multi-page documents are on{" "}
                      <Link to="/dashboard/billing" className="text-brand-300 hover:text-brand-200">
                        paid plans
                      </Link>
                      .
                    </p>
                  )}

                  {error && (
                    <div className="mt-5 flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
                      <AlertCircle size={15} /> {error}
                    </div>
                  )}
                </>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {status === "error" && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          <span className="flex items-center gap-2">
            <AlertCircle size={16} /> {error}
          </span>
          <Button size="sm" variant="secondary" onClick={() => setStatus("selected")}>
            <RotateCcw size={14} /> Try again
          </Button>
        </div>
      )}
    </div>
  );
}

function FileRow({ file, onRemove }) {
  const isImage = file.type.startsWith("image/");
  return (
    <div className="flex items-center gap-3 rounded-lg border border-white/[0.07] bg-white/[0.02] px-3 py-2">
      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-brand-500/15 text-brand-300">
        {isImage ? <ImageIcon size={15} /> : <FileText size={15} />}
      </span>
      <div className="min-w-0 flex-1 text-left">
        <div className="truncate text-sm font-medium text-white">{file.name}</div>
        <div className="text-xs text-slate-500">{formatBytes(file.size)}</div>
      </div>
      {onRemove && (
        <button onClick={onRemove} className="text-slate-500 transition-colors hover:text-red-400" aria-label="Remove">
          <X size={15} />
        </button>
      )}
    </div>
  );
}

function SelectedFiles({
  files,
  canBatch,
  canMultiPage,
  docLabel = "invoice",
  disabled,
  onRemove,
  onAddMore,
  onSingle,
  onBatch,
  onCombine,
  onClear,
}) {
  const multi = files.length > 1;
  const onlyImage = files.length === 1 && files[0].type.startsWith("image/");

  return (
    <div className="w-full max-w-lg">
      {onlyImage ? (
        <div className="relative mx-auto overflow-hidden rounded-xl border border-white/10 bg-ink-950/50">
          <button
            onClick={onClear}
            className="absolute right-2 top-2 z-10 grid h-7 w-7 place-items-center rounded-lg bg-black/50 text-slate-300 backdrop-blur hover:text-white"
            aria-label="Remove file"
          >
            <X size={15} />
          </button>
          <img src={URL.createObjectURL(files[0])} alt={files[0].name} className="max-h-52 w-full object-contain" />
        </div>
      ) : (
        <div className="max-h-56 space-y-2 overflow-auto pr-1">
          {files.map((f, i) => (
            <FileRow key={`${f.name}-${i}`} file={f} onRemove={() => onRemove(i)} />
          ))}
        </div>
      )}

      <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
        <span>{files.length} file{files.length > 1 ? "s" : ""} selected</span>
        {files.length < MAX_FILES && (canBatch || canMultiPage) && (
          <button onClick={onAddMore} type="button" className="text-brand-300 hover:text-brand-200">
            + Add more
          </button>
        )}
      </div>

      <div className="mt-4 flex flex-col items-stretch gap-2">
        {!multi ? (
          <Button onClick={onSingle} disabled={disabled} type="button">
            <Sparkles size={16} /> Extract data
          </Button>
        ) : (
          <>
            {canBatch && (
              <Button onClick={onBatch} disabled={disabled} type="button">
                <Files size={16} /> Extract as {files.length} separate {docLabel}s
              </Button>
            )}
            {canMultiPage && (
              <Button onClick={onCombine} disabled={disabled} variant="secondary" type="button">
                <Layers size={16} /> Combine into one {docLabel}
              </Button>
            )}
          </>
        )}
        <button onClick={onClear} type="button" className="text-xs text-slate-500 hover:text-slate-300">
          Clear all
        </button>
      </div>
    </div>
  );
}

const PROCESS_STEPS = [
  { icon: UploadCloud, label: "Uploading document" },
  { icon: ScanLine, label: "Reading the document" },
  { icon: Sparkles, label: "Structuring fields" },
];

function ProcessingState({ files, combine, uploadPct = 0, docLabel = "invoice" }) {
  // Phase 1: real, determinate upload progress (0–100%).
  // Phase 2: indeterminate server-side extraction (reading → structuring).
  const uploading = uploadPct < 100;
  const [step, setStep] = useState(1); // analysis steps start after upload

  useEffect(() => {
    if (uploading) return;
    const t = setInterval(() => setStep((s) => Math.min(s + 1, PROCESS_STEPS.length - 1)), 1200);
    return () => clearInterval(t);
  }, [uploading]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex min-h-[340px] flex-col items-center justify-center rounded-2xl border border-white/10 bg-white/[0.015] px-6 py-12 text-center"
    >
      <div className="relative mb-6">
        <span className="absolute inset-0 animate-ping rounded-2xl bg-brand-500/20" />
        <span className="relative grid h-16 w-16 place-items-center rounded-2xl bg-brand-gradient text-white shadow-glow">
          {uploading ? <UploadCloud size={26} /> : <Loader2 size={28} className="animate-spin" />}
        </span>
      </div>
      <h3 className="text-lg font-semibold text-white">
        {uploading ? "Uploading…" : `Extracting your ${docLabel}…`}
      </h3>
      <p className="mt-1 max-w-xs text-sm text-slate-500">
        {uploading
          ? `${combine ? `${files.length} pages` : files[0]?.name || "Your file"}`
          : combine
            ? `Merging ${files.length} pages`
            : docLabel === "bank statement"
              ? "Statements have many rows — this can take up to a minute."
              : "Analyzing the document"}
      </p>

      {/* Determinate upload bar */}
      <div className="mt-6 w-full max-w-xs">
        <div className="mb-1.5 flex justify-between text-xs text-slate-500">
          <span>{uploading ? "Upload" : "Uploaded"}</span>
          <span className="tabular-nums">{uploadPct}%</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-white/[0.07]">
          <div
            className="h-full rounded-full bg-brand-gradient transition-[width] duration-200"
            style={{ width: `${Math.max(4, uploadPct)}%` }}
          />
        </div>
      </div>

      {/* Indeterminate analysis steps (after upload completes) */}
      <div className="mt-6 space-y-2.5">
        {PROCESS_STEPS.map((s, i) => {
          const active = !uploading && i === step;
          const done = i === 0 ? !uploading : !uploading && i < step;
          return (
            <div
              key={s.label}
              className={cn(
                "flex items-center gap-3 rounded-lg px-4 py-2 text-sm transition-all",
                active ? "bg-brand-500/10 text-white" : done ? "text-slate-400" : "text-slate-600",
              )}
            >
              <span
                className={cn(
                  "grid h-6 w-6 place-items-center rounded-full",
                  done ? "bg-emerald-500/20 text-emerald-400" : active ? "bg-brand-500/20 text-brand-300" : "bg-white/[0.04]",
                )}
              >
                {done ? <CheckCircle2 size={14} /> : active ? <Loader2 size={13} className="animate-spin" /> : <s.icon size={13} />}
              </span>
              {s.label}
            </div>
          );
        })}
      </div>
    </motion.div>
  );
}

function BatchProgress({ items }) {
  const done = items.filter((i) => i.status === "done" || i.status === "error" || i.status === "skipped").length;
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="rounded-2xl border border-white/10 bg-white/[0.015] p-6"
    >
      <div className="mb-4 flex items-center gap-2.5">
        <Loader2 size={18} className="animate-spin text-brand-300" />
        <h3 className="text-base font-semibold text-white">
          Processing batch — {done} of {items.length}
        </h3>
      </div>
      <div className="space-y-2">
        {items.map((it, i) => (
          <BatchRow key={i} item={it} />
        ))}
      </div>
    </motion.div>
  );
}

function BatchRow({ item }) {
  const map = {
    pending: { icon: <MinusCircle size={15} className="text-slate-600" />, text: "text-slate-500" },
    processing: { icon: <Loader2 size={15} className="animate-spin text-brand-300" />, text: "text-white" },
    done: { icon: <CheckCircle2 size={15} className="text-emerald-400" />, text: "text-slate-200" },
    error: { icon: <AlertCircle size={15} className="text-red-400" />, text: "text-red-300" },
    skipped: { icon: <MinusCircle size={15} className="text-amber-400" />, text: "text-amber-300/80" },
  };
  const s = map[item.status] || map.pending;
  const uploading = item.status === "processing" && typeof item.pct === "number" && item.pct < 100;
  const statusText = uploading
    ? `uploading ${item.pct}%`
    : item.status === "processing"
      ? "extracting…"
      : item.status === "skipped"
        ? "skipped (limit)"
        : item.status === "error"
          ? item.error
          : item.status;
  return (
    <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-sm">
      <div className="flex items-center gap-3">
        <span className="shrink-0">{s.icon}</span>
        <span className={cn("min-w-0 flex-1 truncate", s.text)}>{item.name}</span>
        <span className="shrink-0 text-xs text-slate-500 tabular-nums">{statusText}</span>
      </div>
      {uploading && (
        <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-white/[0.07]">
          <div className="h-full rounded-full bg-brand-gradient transition-[width] duration-200" style={{ width: `${Math.max(4, item.pct)}%` }} />
        </div>
      )}
    </div>
  );
}

function BatchResults({ items, onReset }) {
  const ok = items.filter((i) => i.status === "done");
  const failed = items.filter((i) => i.status === "error" || i.status === "skipped");
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-emerald-500/25 bg-emerald-500/[0.07] px-4 py-3">
        <div className="flex items-center gap-2.5 text-sm text-emerald-200">
          <CheckCircle2 size={18} />
          Batch complete — {ok.length} extracted
          {failed.length > 0 && `, ${failed.length} skipped/failed`}
        </div>
        <Button size="sm" variant="secondary" onClick={onReset}>
          <RotateCcw size={14} /> New batch
        </Button>
      </div>

      {failed.length > 0 && (
        <div className="space-y-2 rounded-xl border border-white/[0.07] bg-white/[0.02] p-3">
          {failed.map((it, i) => (
            <BatchRow key={i} item={it} />
          ))}
        </div>
      )}

      <div className="space-y-4">
        {ok.map((it) => (
          <ResultCard
            key={it.result.id}
            docType={it.result.docType}
            invoice={it.result.invoice}
            extractionId={it.result.id}
            fileName={it.result.fileName}
          />
        ))}
      </div>
    </div>
  );
}

function DocTypeToggle({ value, onChange, disabled, canStatements }) {
  const opts = [
    { id: "invoice", label: "Invoice", icon: FileText },
    { id: "receipt", label: "Receipt", icon: Receipt },
    { id: "statement", label: "Statement", icon: Landmark, locked: !canStatements },
  ];
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <span className="hidden text-sm text-slate-400 sm:inline">Document type</span>
      <div className="inline-flex rounded-xl border border-white/10 bg-white/[0.03] p-1">
        {opts.map((o) => {
          const active = value === o.id;
          return (
            <button
              key={o.id}
              type="button"
              disabled={disabled}
              onClick={() => onChange(o.id)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-sm font-medium transition-all disabled:opacity-50",
                active ? "bg-brand-gradient text-white shadow-glow-sm" : "text-slate-300 hover:text-white",
              )}
            >
              <o.icon size={15} /> {o.label}
              {o.locked && <Lock size={12} className="text-slate-500" />}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function StatementLockBanner() {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-brand-400/25 bg-brand-500/[0.07] px-4 py-3">
      <p className="flex items-start gap-2.5 text-sm text-brand-100">
        <Lock size={16} className="mt-0.5 shrink-0" />
        <span>
          Bank statement extraction is a <span className="font-semibold">Business</span> plan feature.
        </span>
      </p>
      <Button size="sm" to="/dashboard/billing">
        Upgrade
      </Button>
    </div>
  );
}

function StatementAllowanceNote({ stmt }) {
  const remaining = stmt.remaining ?? Math.max(0, stmt.limit - stmt.used);
  const low = remaining <= Math.max(5, Math.round(stmt.limit * 0.1));
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-white/[0.07] bg-white/[0.02] px-4 py-2.5 text-sm">
      <span className="flex items-center gap-2 text-slate-400">
        <Landmark size={15} className="text-brand-300" />
        <span className={cn("font-medium", low ? "text-amber-300" : "text-slate-200")}>
          {stmt.used} of {stmt.limit}
        </span>{" "}
        bank statements used this month
      </span>
      {low && (
        <Link to="/dashboard/billing" className="text-xs font-medium text-brand-300 hover:text-brand-200">
          {remaining} left
        </Link>
      )}
    </div>
  );
}

function StatementLimitBanner({ stmt }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-500/30 bg-amber-500/[0.08] px-4 py-3">
      <div className="flex items-center gap-2.5 text-sm text-amber-200">
        <AlertCircle size={18} />
        You've used all {stmt.limit} bank statements included in your plan this month.
        Invoices and receipts are still unlimited.
      </div>
      <Button size="sm" to="/dashboard/billing">
        View plan
      </Button>
    </div>
  );
}

function LimitBanner({ usage }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-500/30 bg-amber-500/[0.08] px-4 py-3">
      <div className="flex items-center gap-2.5 text-sm text-amber-200">
        <AlertCircle size={18} />
        You've used all {usage.limit} documents on the {usage.planName} plan this month.
      </div>
      <Button size="sm" to="/dashboard/billing">
        Upgrade plan
      </Button>
    </div>
  );
}
