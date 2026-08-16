// Histogram — daily returns distribution, expectancy distribution.

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

interface HistogramProps {
  /** Pre-binned data. Accept both `bins` and `data` for ergonomic call sites. */
  bins?: Array<{ label: string; count: number }>;
  data?: Array<{ label: string; count: number }>;
  height?: number;
  color?: string;
}

export function Histogram({ bins, data, height = 200, color = "#4f46e5" }: HistogramProps) {
  const arr = bins || data || [];
  if (arr.length === 0) {
    return (
      <div className="flex items-center justify-center h-32 text-xs text-slate-400">
        No distribution data
      </div>
    );
  }
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={arr} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
        <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
        <XAxis dataKey="label" tick={{ fontSize: 10, fill: "#64748b" }} tickLine={false} />
        <YAxis
          tick={{ fontSize: 10, fill: "#64748b" }}
          tickLine={false}
          width={40}
          allowDecimals={false}
        />
        <Tooltip
          contentStyle={{ fontSize: 11, border: "1px solid #e2e8f0", borderRadius: 6 }}
          formatter={(v: number) => [v, "Count"]}
        />
        <Bar dataKey="count" fill={color} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}
