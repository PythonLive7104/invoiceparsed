import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { HistoryTable } from "@/components/dashboard/HistoryTable";
import { api } from "@/lib/api";

export default function History() {
  const [items, setItems] = useState(null);

  useEffect(() => {
    let active = true;
    api
      .get("/api/extractions")
      .then(({ data }) => active && setItems(data.extractions))
      .catch(() => active && setItems([]));
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-white sm:text-3xl">
          Extraction history
        </h1>
        <p className="mt-1.5 text-slate-400">
          Every invoice you've processed. Search, review, export or delete.
        </p>
      </div>

      {items === null ? (
        <div className="grid place-items-center py-20">
          <Loader2 className="animate-spin text-brand-400" size={26} />
        </div>
      ) : (
        <HistoryTable initialItems={items} />
      )}
    </div>
  );
}
