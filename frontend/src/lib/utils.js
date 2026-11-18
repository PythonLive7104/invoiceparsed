import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

export function formatMoney(amount, currency) {
  if (amount === null || amount === undefined) return "—";
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: currency || "USD",
      currencyDisplay: "narrowSymbol",
    }).format(amount);
  } catch {
    return `${currency ? currency + " " : ""}${Number(amount).toFixed(2)}`;
  }
}

export function formatDate(value) {
  if (!value) return "—";
  const d = new Date(value);
  if (isNaN(d.getTime())) return typeof value === "string" ? value : "—";
  return d.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(i ? 1 : 0)} ${units[i]}`;
}

export function initials(nameOrEmail) {
  const base = (nameOrEmail || "?").split("@")[0];
  const parts = base.split(/[.\s_-]+/).filter(Boolean);
  return (
    (parts[0]?.[0] ?? "?").toUpperCase() + (parts[1]?.[0] ?? "").toUpperCase()
  );
}

/**
 * Normalize a money/quantity field the user typed, for sending to the API.
 *
 * Deliberately does NOT call Number(): amounts cross the wire as exact decimal
 * strings and the backend parses them with Decimal, so converting to a float
 * here would reintroduce exactly the imprecision the backend works to avoid
 * ("0.07" becoming 0.07000000000000001). Whitespace is trimmed and an empty
 * field becomes null; anything else is passed through untouched and validated
 * server-side, which is the only place that can report a bad value properly.
 */
export function numericInput(v) {
  if (v === null || v === undefined) return null;
  const trimmed = String(v).trim();
  return trimmed === "" ? null : trimmed;
}
