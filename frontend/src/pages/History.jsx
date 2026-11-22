import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Loader2, Search, SlidersHorizontal, X, Download, ChevronLeft, ChevronRight } from "lucide-react";
import { HistoryTable } from "@/components/dashboard/HistoryTable";
import { api, downloadFile } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Processing history.
 *
 * Filtering, searching, sorting and paging all happen on the server. The page
 * used to fetch a flat 300 rows and filter them in the browser, which meant
 * anything older than the most recent 300 documents was invisible AND
 * unsearchable - the data was there, the user just could not reach it.
 */

const EMPTY_FILTERS = {
  q: "",
  status: "",
  validationStatus: "",
  docType: "",
  vendor: "",
  currency: "",
  dateFrom: "",
  dateTo: "",
  amountMin: "",
  amountMax: "",
  reviewed: "",
};

const SELECTS = [
  {
    name: "status", label: "Processing", options: [
      ["", "Any"], ["completed", "Completed"], ["processing", "Processing"], ["failed", "Failed"],
    ],
  },
  {
    name: "validationStatus", label: "Validation", options: [
      ["", "Any"], ["valid", "Valid"], ["valid_with_warnings", "Warnings"],
      ["requires_review", "Needs review"], ["invalid", "Invalid"],
    ],
  },
  {
    name: "docType", label: "Type", options: [
      ["", "Any"], ["invoice", "Invoice"], ["receipt", "Receipt"], ["statement", "Statement"],
    ],
  },
  {
    name: "reviewed", label: "Reviewed", options: [
      ["", "Any"], ["false", "Not yet"], ["true", "Reviewed"],
    ],
  },
];

function toQuery(filters, page, perPage) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== "" && value != null) params.set(key, value);
  }
  params.set("page", page);
  params.set("perPage", perPage);
  return params.toString();
}

export default function History() {
  // Filters live in the URL so a filtered view is shareable and bookmarkable,
  // and so links from elsewhere land where they claim to - the dashboard's
  // "Needs review" tile points here with ?validationStatus=requires_review.
  const [searchParams, setSearchParams] = useSearchParams();
  const [filters, setFilters] = useState(() => {
    const initial = { ...EMPTY_FILTERS };
    for (const key of Object.keys(EMPTY_FILTERS)) {
      const value = searchParams.get(key);
      if (value != null) initial[key] = value;
    }
    return initial;
  });
  const [page, setPage] = useState(() => {
    const value = Number(searchParams.get("page"));
    return Number.isFinite(value) && value > 0 ? value : 1;
  });
  const [perPage] = useState(25);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showFilters, setShowFilters] = useState(false);

  // Debounced so typing in the search box does not fire a request per keystroke.
  const [debounced, setDebounced] = useState(filters);
  const firstLoad = useRef(true);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(filters), firstLoad.current ? 0 : 300);
    firstLoad.current = false;
    return () => clearTimeout(timer);
  }, [filters]);

  const query = useMemo(() => toQuery(debounced, page, perPage), [debounced, page, perPage]);

  useEffect(() => {
    const next = new URLSearchParams();
    for (const [key, value] of Object.entries(debounced)) {
      if (value !== "" && value != null) next.set(key, value);
    }
    if (page > 1) next.set("page", String(page));
    // replace, not push: filtering is not navigation, and a Back button that
    // walks through every keystroke is hostile.
    setSearchParams(next, { replace: true });
  }, [debounced, page, setSearchParams]);

  const load = useCallback(() => {
    let active = true;
    setLoading(true);
    api
      .get(`/api/extractions?${query}`)
      .then(({ data: body }) => active && setData(body))
      .catch(() => active && setData({ extractions: [], total: 0, pages: 1 }))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [query]);

  useEffect(() => load(), [load]);

  function setFilter(name, value) {
    setFilters((prev) => ({ ...prev, [name]: value }));
    setPage(1); // a new filter always starts at the first page
  }

  const activeCount = Object.entries(filters).filter(
    ([key, value]) => key !== "q" && value !== "",
  ).length;

  const items = data?.extractions ?? [];
  const total = data?.total ?? 0;
  const pages = data?.pages ?? 1;
  // Distinguishes "no documents at all" from "none match these filters".
  const hasFilters = activeCount > 0 || filters.q !== "";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-white sm:text-3xl">
            Processing history
          </h1>
          <p className="mt-1.5 text-slate-400">
            {total > 0
              ? `${total.toLocaleString()} document${total === 1 ? "" : "s"} processed.`
              : "Every document you've processed."}
          </p>
        </div>
        <button
          onClick={() => downloadFile(`/api/extractions/export?${query}`, "processing-history.csv")}
          className="inline-flex h-10 items-center gap-2 rounded-xl border border-white/10 px-3.5 text-sm text-slate-300 transition-colors hover:bg-white/[0.06] hover:text-white"
          title="Export the rows matching these filters"
        >
          <Download size={15} /> Export CSV
        </button>
      </div>

      {/* Search + filter toggle */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-[240px] flex-1 max-w-sm">
          <Search size={16} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            value={filters.q}
            onChange={(e) => setFilter("q", e.target.value)}
            placeholder="Search supplier, invoice #, file…"
            className="h-11 w-full rounded-xl border border-white/10 bg-ink-900/60 pl-10 pr-3.5 text-sm text-white placeholder:text-slate-600 outline-none focus:border-brand-400/60 focus:ring-2 focus:ring-brand-400/20"
          />
        </div>
        <button
          onClick={() => setShowFilters((v) => !v)}
          className={cn(
            "inline-flex h-11 items-center gap-2 rounded-xl border px-3.5 text-sm transition-colors",
            showFilters || activeCount
              ? "border-brand-400/50 bg-brand-500/10 text-brand-200"
              : "border-white/10 text-slate-300 hover:bg-white/[0.06]",
          )}
        >
          <SlidersHorizontal size={15} /> Filters
          {activeCount > 0 && (
            <span className="rounded-full bg-brand-500/30 px-1.5 text-xs">{activeCount}</span>
          )}
        </button>
        {hasFilters && (
          <button
            onClick={() => {
              setFilters(EMPTY_FILTERS);
              setPage(1);
            }}
            className="inline-flex h-11 items-center gap-1.5 text-sm text-slate-400 hover:text-white"
          >
            <X size={14} /> Clear
          </button>
        )}
      </div>

      {showFilters && (
        <div className="glass grid gap-4 rounded-2xl p-5 sm:grid-cols-2 lg:grid-cols-4">
          {SELECTS.map(({ name, label, options }) => (
            <label key={name} className="block">
              <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-500">
                {label}
              </span>
              <select
                value={filters[name]}
                onChange={(e) => setFilter(name, e.target.value)}
                className="h-10 w-full rounded-lg border border-white/10 bg-ink-900/60 px-3 text-sm text-white outline-none focus:border-brand-400/60"
              >
                {options.map(([value, text]) => (
                  <option key={value} value={value}>{text}</option>
                ))}
              </select>
            </label>
          ))}

          <Field label="Supplier" value={filters.vendor}
            onChange={(v) => setFilter("vendor", v)} placeholder="Acme Ltd" />
          <Field label="Currency" value={filters.currency}
            onChange={(v) => setFilter("currency", v)} placeholder="USD" />
          <Field label="From" type="date" value={filters.dateFrom}
            onChange={(v) => setFilter("dateFrom", v)} />
          <Field label="To" type="date" value={filters.dateTo}
            onChange={(v) => setFilter("dateTo", v)} />
          <Field label="Min amount" type="number" value={filters.amountMin}
            onChange={(v) => setFilter("amountMin", v)} placeholder="0.00" />
          <Field label="Max amount" type="number" value={filters.amountMax}
            onChange={(v) => setFilter("amountMax", v)} placeholder="0.00" />
        </div>
      )}

      {loading && data === null ? (
        <div className="grid place-items-center py-20">
          <Loader2 className="animate-spin text-brand-400" size={26} />
        </div>
      ) : (
        <div className={cn(loading && "opacity-60 transition-opacity")}>
          <HistoryTable
            items={items}
            emptyState={hasFilters ? "filtered" : "none"}
            onChanged={load}
          />
        </div>
      )}

      {pages > 1 && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-slate-500">
            Page {page} of {pages}
          </span>
          <div className="flex gap-2">
            <PageButton disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              <ChevronLeft size={15} /> Previous
            </PageButton>
            <PageButton disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>
              Next <ChevronRight size={15} />
            </PageButton>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, value, onChange, type = "text", placeholder }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </span>
      <input
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="h-10 w-full rounded-lg border border-white/10 bg-ink-900/60 px-3 text-sm text-white placeholder:text-slate-600 outline-none focus:border-brand-400/60"
      />
    </label>
  );
}

function PageButton({ disabled, onClick, children }) {
  return (
    <button
      disabled={disabled}
      onClick={onClick}
      className="inline-flex h-9 items-center gap-1 rounded-lg border border-white/10 px-3 text-sm text-slate-300 transition-colors hover:bg-white/[0.06] hover:text-white disabled:opacity-40 disabled:hover:bg-transparent"
    >
      {children}
    </button>
  );
}
