// Decimal helpers — never NaN, never fabricate.
// Per 02/07/09: numbers arrive as STRINGS; convert at render-time only;
// a null/empty value stays null (renders as "--"), never 0.

/** Convert a string|number|null to a number, returning null on null/empty/NaN. */
export function toNum(v: string | number | null | undefined): number | null {
  if (v === null || v === undefined) return null;
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  const s = v.trim();
  if (s === "" || s === "null") return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

/** True if a value is null/empty/`"null"` (treat as missing). */
export function isMissing(v: unknown): boolean {
  if (v === null || v === undefined) return true;
  if (typeof v === "string") {
    const s = v.trim();
    return s === "" || s === "null" || s === "None";
  }
  return false;
}

/** Display string for a possibly-null decimal/ratio: `--` for missing. */
export function fmtDecimal(v: string | number | null | undefined, digits = 2): string {
  if (isMissing(v)) return "--";
  const n = toNum(v);
  if (n === null) return "--";
  return n.toLocaleString("en-IN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/** INR money format: ₹1,234.56. */
export function fmtInr(v: string | number | null | undefined, digits = 2): string {
  if (isMissing(v)) return "--";
  const n = toNum(v);
  if (n === null) return "--";
  const formatted = Math.abs(n).toLocaleString("en-IN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  return `${n < 0 ? "−₹" : "₹"}${formatted}`;
}

/** Percent format: 12.34%. */
export function fmtPct(v: string | number | null | undefined, digits = 2): string {
  if (isMissing(v)) return "--";
  const n = toNum(v);
  if (n === null) return "--";
  return `${n.toLocaleString("en-IN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}%`;
}

/** Ratio format (no %): Sharpe/Sortino/profit factor — 2 dp. */
export function fmtRatio(v: string | number | null | undefined, digits = 2): string {
  return fmtDecimal(v, digits);
}

/** Integer format with thousands separators. */
export function fmtInt(v: string | number | null | undefined): string {
  if (isMissing(v)) return "--";
  const n = toNum(v);
  if (n === null) return "--";
  return Math.trunc(n).toLocaleString("en-IN");
}

/** Sign-aware color token: profit green / loss red / neutral slate. */
export function pnlColor(v: string | number | null | undefined): string {
  if (isMissing(v)) return "text-slate-500";
  const n = toNum(v);
  if (n === null) return "text-slate-500";
  if (n > 0) return "text-emerald-600";
  if (n < 0) return "text-rose-600";
  return "text-slate-500";
}
