// Chip / Badge — status, regime, rule_id, ADR-029 gate, run status.

import type { ReactNode } from "react";

type ChipTone =
  | "neutral"
  | "indigo"
  | "blue"
  | "emerald"
  | "rose"
  | "amber"
  | "violet"
  | "sky"
  | "slate";

const TONES: Record<ChipTone, string> = {
  neutral: "bg-slate-100 text-slate-700 border-slate-200",
  indigo: "bg-indigo-50 text-indigo-700 border-indigo-200",
  blue: "bg-blue-50 text-blue-700 border-blue-200",
  emerald: "bg-emerald-50 text-emerald-700 border-emerald-200",
  rose: "bg-rose-50 text-rose-700 border-rose-200",
  amber: "bg-amber-50 text-amber-800 border-amber-200",
  violet: "bg-violet-50 text-violet-700 border-violet-200",
  sky: "bg-sky-50 text-sky-700 border-sky-200",
  slate: "bg-slate-50 text-slate-600 border-slate-200",
};

interface ChipProps {
  children: ReactNode;
  tone?: ChipTone;
  className?: string;
}

export function Chip({ children, tone = "neutral", className = "" }: ChipProps) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-md border ${TONES[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

/** Map a regime string to a pastel chip tone (deterministic by hash). */
const REGIME_TONES: ChipTone[] = [
  "emerald",
  "sky",
  "violet",
  "amber",
  "blue",
  "rose",
  "indigo",
  "slate",
];

export function regimeTone(regime: string | null | undefined): ChipTone {
  if (!regime) return "slate";
  let h = 0;
  for (let i = 0; i < regime.length; i++) h = (h * 31 + regime.charCodeAt(i)) >>> 0;
  return REGIME_TONES[h % REGIME_TONES.length];
}

/** ADR-029 gate status → tone. */
export function gateTone(status: string | null | undefined): ChipTone {
  switch (status) {
    case "GO":
      return "emerald";
    case "NO_GO":
      return "rose";
    case "INSUFFICIENT_DATA":
      return "amber";
    default:
      return "slate";
  }
}

/** Backtest run status → tone. */
export function runStatusTone(status: string | null | undefined): ChipTone {
  switch (status) {
    case "COMPLETED":
      return "emerald";
    case "RUNNING":
      return "blue";
    case "PENDING":
      return "amber";
    case "FAILED":
      return "rose";
    default:
      return "slate";
  }
}

/** Cost-sensitivity classification → tone. */
export function classificationTone(c: string | null | undefined): ChipTone {
  switch (c) {
    case "BREAKEVEN_FOUND":
      return "amber";
    case "NEVER_PROFITABLE":
      return "rose";
    case "SURVIVES_FULL_RANGE":
      return "emerald";
    default:
      return "slate";
  }
}

/** has_edge (true/false/null) → tone; null = insufficient data (amber, distinct). */
export function hasEdgeTone(v: boolean | null | undefined): ChipTone {
  if (v === true) return "emerald";
  if (v === false) return "rose";
  return "amber";
}
