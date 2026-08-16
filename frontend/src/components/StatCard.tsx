// StatCard — label + value + optional delta. Coloring by sign, not direction.

import type { ReactNode } from "react";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

interface StatCardProps {
  label: string;
  value: ReactNode;
  /** Delta text, e.g. "+1.2%" or "-0.4%". When omitted, no delta rendered. */
  delta?: string | null;
  /** "up" | "down" | "neutral" — drives icon + color. Defaults to neutral. */
  deltaDirection?: "up" | "down" | "neutral";
  hint?: ReactNode;
}

export function StatCard({
  label,
  value,
  delta,
  deltaDirection = "neutral",
  hint,
}: StatCardProps) {
  const color =
    deltaDirection === "up"
      ? "text-emerald-600"
      : deltaDirection === "down"
      ? "text-rose-600"
      : "text-slate-500";
  const Icon =
    deltaDirection === "up"
      ? ArrowUpRight
      : deltaDirection === "down"
      ? ArrowDownRight
      : Minus;
  return (
    <div className="bg-white border border-slate-200 shadow-sm rounded-lg p-4 flex flex-col gap-1">
      <span className="text-xs uppercase tracking-wide text-slate-500">
        {label}
      </span>
      <span className="text-2xl font-semibold text-slate-900 tabular-nums">
        {value}
      </span>
      {delta && (
        <span className={`text-xs ${color} flex items-center gap-1`}>
          <Icon className="w-3 h-3" />
          {delta}
        </span>
      )}
      {hint && <span className="text-xs text-slate-400">{hint}</span>}
    </div>
  );
}
