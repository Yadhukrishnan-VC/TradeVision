// EquityCurve — area+line chart of cumulative PnL.
// Per 06_CHARTS.md: equity curve is built from stats.trades[].net_pnl cumulative
// OR stats.in_sample.equity_curve / out_of_sample.equity_curve arrays.

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Line,
  ComposedChart,
} from "recharts";
import { toNum } from "@/lib/decimal";

interface EquityCurveProps {
  /** Pre-computed cumulative series. Either this or `decimals` must be provided. */
  series?: Array<{ label: string; value: number | null }>;
  /** Raw decimal strings (e.g. trades[].net_pnl) — auto-cumulative. */
  decimals?: string[];
  /** Initial capital (added to the cumulative). Defaults to 0. */
  initialEquity?: number;
  height?: number;
  /** When true, render as a single line (no area). Defaults to false (area+line). */
  lineOnly?: boolean;
}

export function EquityCurve({
  series,
  decimals,
  initialEquity = 0,
  height = 240,
  lineOnly = false,
}: EquityCurveProps) {
  let data: Array<{ label: string; value: number | null }> = [];
  if (series) {
    data = series;
  } else if (decimals) {
    let cum = initialEquity;
    data = decimals.map((d, i) => {
      const v = toNum(d);
      if (v !== null) cum += v;
      return { label: `#${i + 1}`, value: cum };
    });
  }
  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-32 text-xs text-slate-400">
        No equity data
      </div>
    );
  }
  const Chart = lineOnly ? ComposedChart : AreaChart;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <Chart data={data} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
        <defs>
          <linearGradient id="tvEquityFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#4f46e5" stopOpacity={0.3} />
            <stop offset="100%" stopColor="#4f46e5" stopOpacity={0.05} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="var(--tv-chart-grid)" strokeDasharray="3 3" />
        <XAxis dataKey="label" tick={{ fontSize: 10, fill: "var(--tv-chart-tick)" }} tickLine={false} />
        <YAxis
          tick={{ fontSize: 10, fill: "var(--tv-chart-tick)" }}
          tickLine={false}
          width={56}
          tickFormatter={(v: number) =>
            v.toLocaleString("en-IN", { notation: "compact", maximumFractionDigits: 1 })
          }
        />
        <Tooltip
          contentStyle={{
            fontSize: 11,
            border: "1px solid var(--tv-chart-tooltip-border)",
            borderRadius: 6,
          }}
          formatter={(v: number) => [`₹${v.toLocaleString("en-IN")}`, "Equity"]}
        />
        {!lineOnly && (
          <Area
            type="monotone"
            dataKey="value"
            stroke="#4f46e5"
            strokeWidth={1.5}
            fill="url(#tvEquityFill)"
            isAnimationActive={false}
          />
        )}
        {lineOnly && (
          <Line
            type="monotone"
            dataKey="value"
            stroke="#4f46e5"
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        )}
      </Chart>
    </ResponsiveContainer>
  );
}
