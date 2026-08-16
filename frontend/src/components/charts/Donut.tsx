// Donut chart — portfolio composition allocation_pct, regime share, etc.

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

interface DonutProps {
  data: Array<{ label: string; value: number; tone?: string }>;
  height?: number;
  /** Center label (e.g. total). */
  centerLabel?: string;
  centerValue?: string;
}

const PALETTE = [
  "#4f46e5",
  "#0ea5e9",
  "#10b981",
  "#f59e0b",
  "#ef4444",
  "#8b5cf6",
  "#06b6d4",
  "#84cc16",
  "#ec4899",
  "#64748b",
];

export function Donut({ data, height = 240, centerLabel, centerValue }: DonutProps) {
  const total = data.reduce((s, d) => s + (Number.isFinite(d.value) ? d.value : 0), 0);
  if (total === 0 || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-32 text-xs text-slate-400">
        No allocation data
      </div>
    );
  }
  return (
    <div className="relative" style={{ height }}>
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            nameKey="label"
            cx="50%"
            cy="50%"
            innerRadius="55%"
            outerRadius="85%"
            paddingAngle={1}
            isAnimationActive={false}
          >
            {data.map((d, i) => (
              <Cell key={i} fill={d.tone || PALETTE[i % PALETTE.length]} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{ fontSize: 11, border: "1px solid #e2e8f0", borderRadius: 6 }}
            formatter={(v: number, n: string) => [
              `${v.toLocaleString("en-IN", { maximumFractionDigits: 2 })} (${((v / total) * 100).toFixed(1)}%)`,
              n,
            ]}
          />
        </PieChart>
      </ResponsiveContainer>
      {(centerLabel || centerValue) && (
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          {centerLabel && (
            <span className="text-[10px] uppercase tracking-wide text-slate-500">
              {centerLabel}
            </span>
          )}
          {centerValue && (
            <span className="text-sm font-semibold text-slate-900 tabular-nums">
              {centerValue}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
