import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Clock, FileText, Loader2 } from "lucide-react";
import { ResultCard } from "@/components/dashboard/ResultCard";
import { api } from "@/lib/api";
import { formatBytes, formatDate } from "@/lib/utils";

export default function ExtractionDetail() {
  const { id } = useParams();
  const [row, setRow] = useState(null);
  const [error, setError] = useState(false);

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

  return (
    <div className="space-y-6">
      <Link
        to="/dashboard/history"
        className="inline-flex items-center gap-1.5 text-sm text-slate-400 transition-colors hover:text-white"
      >
        <ArrowLeft size={16} /> Back to history
      </Link>

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
          </div>

          {row.status === "completed" && row.invoice ? (
            <ResultCard docType={row.docType} invoice={row.invoice} extractionId={row.id} fileName={row.fileName} initialShowDoc />
          ) : (
            <div className="glass rounded-2xl p-8 text-center">
              <h2 className="text-lg font-semibold text-white">This extraction failed</h2>
              <p className="mt-2 text-sm text-slate-400">
                We couldn't extract data from this file. Try uploading a clearer copy.
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
