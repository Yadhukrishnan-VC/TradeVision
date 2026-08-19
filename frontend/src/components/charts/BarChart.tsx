// BarChart wrapper — used for regime breakdown, walk-forward windows, etc.

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface BarChartProps {
  data: Array<{ label: string; value: number | null; tone?: string }>;
  height?: number;
  /** Color override; defaults to indigo-600. */
  color?: string;
  /** Format Y axis ticks (default: compact number). */
  yTickFormatter?: (v: number) => string;
  /** Tooltip value formatter. */
  tooltipFormatter?: (v: number) => string;
  /** Layout orientation. */
  layout?: "horizontal" | "vertical";
  /** When true (vertical layout), labels live on Y axis (good for long labels). */
  numeric?: boolean;
}

export function BarChartTV({
  data,
  height = 240,
  color = "#4f46e5",
  yTickFormatter,
  tooltipFormatter,
  layout = "horizontal",
}: BarChartProps) {
  const fmt = yTickFormatter || ((v: number) =>
    v.toLocaleString("en-IN", { notation: "compact", maximumFractionDigits: 1 })
  );
  const ttip = tooltipFormatter || ((v: number) => v.toLocaleString("en-IN"));
  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-32 text-xs text-slate-400">
        No data
      </div>
    );
  }
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart
        data={data}
        layout={layout}
        margin={{ top: 8, right: 8, bottom: 8, left: 0 }}
      >
        <CartesianGrid stroke="var(--tv-chart-grid)" strokeDasharray="3 3" />
        {layout === "horizontal" ? (
          <>
            <XAxis dataKey="label" tick={{ fontSize: 10, fill: "var(--tv-chart-tick)" }} tickLine={false} />
            <YAxis
              tick={{ fontSize: 10, fill: "var(--tv-chart-tick)" }}
              tickLine={false}
              width={56}
              tickFormatter={fmt}
            />
          </>
        ) : (
          <>
            <XAxis type="number" tick={{ fontSize: 10, fill: "var(--tv-chart-tick)" }} tickLine={false} tickFormatter={fmt} />
            <YAxis
              type="category"
              dataKey="label"
              tick={{ fontSize: 10, fill: "var(--tv-chart-tick)" }}
              tickLine={false}
              width={120}
            />
          </>
        )}
        <Tooltip
          contentStyle={{ fontSize: 11, border: "1px solid var(--tv-chart-tooltip-border)", borderRadius: 6 }}
          formatter={(v: number) => [ttip(v), "Value"]}
        />
        <Bar dataKey="value" fill={color} isAnimationActive={false}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.tone || color} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
