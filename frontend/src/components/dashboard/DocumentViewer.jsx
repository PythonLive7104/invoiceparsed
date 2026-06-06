import { useEffect, useState } from "react";
import { Loader2, FileWarning, ChevronLeft, ChevronRight } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Renders the stored original file(s) for an extraction, fetched with auth. */
export function DocumentViewer({ extractionId }) {
  const [files, setFiles] = useState(null);
  const [idx, setIdx] = useState(0);
  const [url, setUrl] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    api
      .get(`/api/extractions/${extractionId}/files`)
      .then(({ data }) => active && setFiles(data.files || []))
      .catch(() => active && setError(true));
    return () => {
      active = false;
    };
  }, [extractionId]);

  useEffect(() => {
    if (!files || files.length === 0) {
      setLoading(false);
      return;
    }
    let active = true;
    let objUrl;
    setLoading(true);
    api
      .get(`/api/extractions/${extractionId}/file/${files[idx].index}`, { responseType: "blob" })
      .then(({ data }) => {
        if (!active) return;
        objUrl = URL.createObjectURL(data);
        setUrl(objUrl);
        setLoading(false);
      })
      .catch(() => {
        if (!active) return;
        setError(true);
        setLoading(false);
      });
    return () => {
      active = false;
      if (objUrl) URL.revokeObjectURL(objUrl);
    };
  }, [files, idx, extractionId]);

  if (error) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-white/[0.07] bg-white/[0.02] px-4 py-6 text-sm text-slate-400">
        <FileWarning size={16} /> Couldn't load the original document.
      </div>
    );
  }
  if (files === null) {
    return (
      <div className="grid place-items-center rounded-xl border border-white/[0.07] bg-white/[0.02] py-16">
        <Loader2 className="animate-spin text-brand-400" size={22} />
      </div>
    );
  }
  if (files.length === 0) {
    return (
      <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] px-4 py-6 text-center text-sm text-slate-500">
        No original document stored for this extraction.
      </div>
    );
  }

  const current = files[idx];
  const isPdf =
    current.mime === "application/pdf" || current.name.toLowerCase().endsWith(".pdf");

  return (
    <div className="rounded-xl border border-white/[0.07] bg-ink-950/50 p-2">
      {files.length > 1 && (
        <div className="mb-2 flex items-center justify-between px-1">
          <button
            onClick={() => setIdx((i) => Math.max(0, i - 1))}
            disabled={idx === 0}
            className="grid h-8 w-8 place-items-center rounded-lg text-slate-400 hover:bg-white/[0.06] disabled:opacity-40"
          >
            <ChevronLeft size={16} />
          </button>
          <span className="truncate text-xs text-slate-400">
            Page {idx + 1} of {files.length} · {current.name}
          </span>
          <button
            onClick={() => setIdx((i) => Math.min(files.length - 1, i + 1))}
            disabled={idx === files.length - 1}
            className="grid h-8 w-8 place-items-center rounded-lg text-slate-400 hover:bg-white/[0.06] disabled:opacity-40"
          >
            <ChevronRight size={16} />
          </button>
        </div>
      )}

      <div className={cn("relative overflow-hidden rounded-lg bg-black/30", loading && "min-h-[300px]")}>
        {loading && (
          <div className="absolute inset-0 grid place-items-center">
            <Loader2 className="animate-spin text-brand-400" size={22} />
          </div>
        )}
        {url && !loading && (
          isPdf ? (
            <iframe src={url} title={current.name} className="h-[600px] w-full bg-white" />
          ) : (
            <img src={url} alt={current.name} className="mx-auto max-h-[600px] w-full object-contain" />
          )
        )}
      </div>
    </div>
  );
}
