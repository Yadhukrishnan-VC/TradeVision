// LineChart wrapper — used for cost sensitivity series (expectancy vs cost).

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface LineChartProps {
  data: Array<{ x: number; y: number | null }>;
  height?: number;
  color?: string;
  xLabel?: string;
  yLabel?: string;
  /** Optional breakeven marker (x coordinate). */
  breakevenX?: number | null;
  breakevenLabel?: string;
  xTickFormatter?: (v: number) => string;
  yTickFormatter?: (v: number) => string;
  tooltipFormatter?: (v: number) => string;
}

export function LineChartTV({
  data,
  height = 240,
  color = "#4f46e5",
  xLabel,
  yLabel,
  breakevenX,
  breakevenLabel = "Breakeven",
  xTickFormatter,
  yTickFormatter,
  tooltipFormatter,
}: LineChartProps) {
  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-32 text-xs text-slate-400">
        No series
      </div>
    );
  }
  const fmtX = xTickFormatter || ((v: number) => v.toLocaleString("en-IN", { maximumFractionDigits: 2 }));
  const fmtY = yTickFormatter || ((v: number) => v.toLocaleString("en-IN", { maximumFractionDigits: 2 }));
  const ttip = tooltipFormatter || fmtY;
  const breakevenPoint =
    breakevenX !== null && breakevenX !== undefined
      ? data.find((d) => Math.abs(d.x - breakevenX) < 1e-9) || null
      : null;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 16, left: 0 }}>
        <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
        <XAxis
          dataKey="x"
          type="number"
          tick={{ fontSize: 10, fill: "#64748b" }}
          tickLine={false}
          tickFormatter={fmtX}
          label={xLabel ? { value: xLabel, position: "insideBottom", offset: -8, fontSize: 10, fill: "#64748b" } : undefined}
        />
        <YAxis
          tick={{ fontSize: 10, fill: "#64748b" }}
          tickLine={false}
          width={56}
          tickFormatter={fmtY}
          label={yLabel ? { value: yLabel, angle: -90, position: "insideLeft", fontSize: 10, fill: "#64748b" } : undefined}
        />
        <Tooltip
          contentStyle={{ fontSize: 11, border: "1px solid #e2e8f0", borderRadius: 6 }}
          formatter={(v: number) => [ttip(v), yLabel || "Value"]}
          labelFormatter={(l: number) => `${xLabel || "x"}: ${fmtX(l)}`}
        />
        <Line
          type="monotone"
          dataKey="y"
          stroke={color}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
          connectNulls
        />
        {breakevenPoint && breakevenPoint.y !== null && (
          <ReferenceDot
            x={breakevenPoint.x}
            y={breakevenPoint.y}
            r={4}
            fill="#f59e0b"
            stroke="#fff"
            strokeWidth={1}
            label={{
              value: breakevenLabel,
              position: "top",
              fontSize: 10,
              fill: "#b45309",
            }}
          />
        )}
      </LineChart>
    </ResponsiveContainer>
  );
}
