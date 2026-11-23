import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Clock, FileText, Loader2, Columns2, Rows3 } from "lucide-react";
import { ResultCard } from "@/components/dashboard/ResultCard";
import { DocumentViewer } from "@/components/dashboard/DocumentViewer";
import { api } from "@/lib/api";
import { cn, formatBytes, formatDate } from "@/lib/utils";

/**
 * Document review.
 *
 * Split-screen on wide viewports: the original document on the left, the
 * extracted fields on the right. Checking a number against the source is the
 * whole job here, and doing that by scrolling between two stacked panels is
 * where mistakes get missed.
 *
 * The document column is sticky, so it stays in view while the (much taller)
 * fields column scrolls. Below xl the two stack, because side-by-side on a
 * narrow screen makes both halves unusable.
 */
export default function ExtractionDetail() {
  const { id } = useParams();
  const [row, setRow] = useState(null);
  const [error, setError] = useState(false);
  const [split, setSplit] = useState(true);

  useEffect(() => {
    let active = true;
    api
      .get(`/api/extractions/${id}`)
      .then(({ data }) => active && setRow(data))
      .catch(() => active && setError(true));
    return () => {
      active = false;
    };
  }, [id]);

  const reviewable = row?.status === "completed" && row?.invoice;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link
          to="/dashboard/history"
          className="inline-flex items-center gap-1.5 text-sm text-slate-400 transition-colors hover:text-white"
        >
          <ArrowLeft size={16} /> Back to history
        </Link>

        {reviewable && (
          <button
            onClick={() => setSplit((v) => !v)}
            className="hidden items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-xs font-medium text-slate-300 transition-colors hover:bg-white/[0.06] hover:text-white xl:inline-flex"
            title={split ? "Show the fields full width" : "Show the document alongside"}
          >
            {split ? <Rows3 size={14} /> : <Columns2 size={14} />}
            {split ? "Full width" : "Side by side"}
          </button>
        )}
      </div>

      {error ? (
        <div className="glass rounded-2xl p-8 text-center">
          <h2 className="text-lg font-semibold text-white">Extraction not found</h2>
          <p className="mt-2 text-sm text-slate-400">It may have been deleted.</p>
        </div>
      ) : row === null ? (
        <div className="grid place-items-center py-20">
          <Loader2 className="animate-spin text-brand-400" size={26} />
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-slate-500">
            <span className="flex items-center gap-1.5">
              <FileText size={15} /> {row.fileName}
            </span>
            <span className="flex items-center gap-1.5">
              <Clock size={15} /> {formatDate(row.createdAt)}
            </span>
            <span>{formatBytes(row.fileSize)}</span>
            {row.processingMs != null && (
              <span>{(row.processingMs / 1000).toFixed(1)}s to extract</span>
            )}
          </div>

          {reviewable ? (
            <div
              className={cn(
                "grid gap-5",
                split && "xl:grid-cols-2 xl:items-start",
              )}
            >
              {split && (
                <div className="xl:sticky xl:top-6">
                  <div className="glass overflow-hidden rounded-2xl p-4">
                    <DocumentViewer extractionId={row.id} />
                  </div>
                </div>
              )}
              <div className="min-w-0">
                <ResultCard
                  docType={row.docType}
                  invoice={row.invoice}
                  validation={row.validation}
                  duplicates={row.duplicates}
                  corrections={row.corrections}
                  poMatch={row.poMatch}
                  extractionId={row.id}
                  fileName={row.fileName}
                  splitView={split}
                  initialShowDoc={!split}
                />
              </div>
            </div>
          ) : (
            <div className="glass rounded-2xl p-8 text-center">
              <h2 className="text-lg font-semibold text-white">This extraction failed</h2>
              <p className="mt-2 text-sm text-slate-400">
                {row.errorMessage ||
                  "We couldn't extract data from this file. Try uploading a clearer copy."}
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
