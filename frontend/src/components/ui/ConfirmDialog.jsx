import { useEffect } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";

/**
 * Accessible, animated confirmation modal. Renders into <body> via a portal so
 * it's never clipped by overflow/stacking contexts.
 *
 *   <ConfirmDialog
 *     open={open}
 *     title="Delete this extraction?"
 *     description="This permanently removes the record and its files."
 *     confirmLabel="Delete"
 *     loading={busy}
 *     onConfirm={doDelete}
 *     onClose={() => setOpen(false)}
 *   />
 */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  tone = "danger", // danger | default
  loading = false,
  disabled = false,
  onConfirm,
  onClose,
  children,
}) {
  // Escape to dismiss + lock background scroll while open.
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if (e.key === "Escape" && !loading) onClose?.();
    };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [open, loading, onClose]);

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[100] flex items-center justify-center p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <div
            className="absolute inset-0 bg-black/70 backdrop-blur-sm"
            onClick={() => !loading && onClose?.()}
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label={typeof title === "string" ? title : undefined}
            initial={{ opacity: 0, scale: 0.96, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 10 }}
            transition={{ duration: 0.15 }}
            className="glass relative w-full max-w-md rounded-2xl border border-white/10 p-6 shadow-glow"
          >
            <button
              onClick={() => !loading && onClose?.()}
              className="absolute right-4 top-4 text-slate-500 transition-colors hover:text-white"
              aria-label="Close"
              type="button"
            >
              <X size={18} />
            </button>

            <div className="flex items-start gap-3 pr-6">
              <span
                className={cn(
                  "grid h-10 w-10 shrink-0 place-items-center rounded-xl",
                  tone === "danger" ? "bg-red-500/15 text-red-300" : "bg-brand-500/15 text-brand-300",
                )}
              >
                <AlertTriangle size={20} />
              </span>
              <div className="min-w-0">
                <h2 className="text-lg font-semibold text-white">{title}</h2>
                {description && (
                  <p className="mt-1.5 text-sm leading-relaxed text-slate-400">{description}</p>
                )}
              </div>
            </div>

            {children && <div className="mt-4">{children}</div>}

            <div className="mt-6 flex justify-end gap-3">
              <Button variant="secondary" size="sm" onClick={onClose} disabled={loading} type="button">
                {cancelLabel}
              </Button>
              <button
                onClick={onConfirm}
                disabled={loading || disabled}
                type="button"
                className={cn(
                  "inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium text-white transition-colors disabled:cursor-not-allowed disabled:opacity-50",
                  tone === "danger" ? "bg-red-500/90 hover:bg-red-500" : "bg-brand-gradient",
                )}
              >
                {loading && <Loader2 size={15} className="animate-spin" />}
                {confirmLabel}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
