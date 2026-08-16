// Walk-Forward page — POST /backtesting/walk-forward/.
// Per 04_API_CONTRACT.md: VERIFIED request + response shape.

import { useMemo, useState, type FormEvent } from "react";
import { Card } from "@/components/Card";
import { Alert } from "@/components/Alert";
import { StatCard } from "@/components/StatCard";
import { Chip } from "@/components/Chip";
import { EmptyState } from "@/components/EmptyState";
import { BarChartTV } from "@/components/charts";
import { Field, ResearchActions, SyncResearchWarning, useSyncResearch } from "./_research-utils";
import { runWalkForward } from "@/api/research";
import { toIso, todayDate } from "@/lib/time";
import { fmtDecimal, fmtPct, fmtRatio, toNum } from "@/lib/decimal";
import type {
  WalkForwardRequest,
  WalkForwardResponse,
  WalkForwardDistributionEntry,
} from "@/types/research";

export function WalkForward() {
  const [symbol, setSymbol] = useState("RELIANCE");
  const [timeframe, setTimeframe] = useState("15min");
  const [rangeStart, setRangeStart] = useState(todayDate());
  const [rangeEnd, setRangeEnd] = useState(todayDate());
  const [windowSize, setWindowSize] = useState("30");
  const [stepSize, setStepSize] = useState("10");
  const [inSampleRatio, setInSampleRatio] = useState("0.70");
  const [initialCapital, setInitialCapital] = useState("1000000");

  const buildRequest = (): WalkForwardRequest => ({
    symbol: symbol.toUpperCase(),
    timeframe: timeframe || undefined,
    range_start: toIso(rangeStart, "00:00"),
    range_end: toIso(rangeEnd, "23:59"),
    window_size_days: Number(windowSize),
    step_size_days: Number(stepSize),
    in_sample_ratio: inSampleRatio || undefined,
    initial_capital: initialCapital || undefined,
  });

  const { loading, data, error, timedOut, submit, reset } =
    useSyncResearch<WalkForwardResponse>(() => runWalkForward(buildRequest()));

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (loading) return;
    submit();
  }

  // Per-window bar chart: OOS expectancy per window index.
  const windowBars = useMemo(() => {
    if (!data?.windows) return [];
    return data.windows.map((w) => ({
      label: `W${w.window_index + 1}`,
      value: toNum(w.out_of_sample_expectancy),
      tone: (toNum(w.out_of_sample_expectancy) ?? 0) >= 0 ? "#10b981" : "#ef4444",
    }));
  }, [data]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Walk-Forward Validation</h1>
        <p className="text-sm text-slate-500 mt-1">
          Rolling OOS validation across sliding time windows.
        </p>
      </div>

      <Card title="Configuration" description="POST /backtesting/walk-forward/">
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Field label="Symbol">
              <input className="tv-input" value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} required disabled={loading} />
            </Field>
            <Field label="Timeframe" hint="optional, e.g. 15min, 1D">
              <input className="tv-input" value={timeframe} onChange={(e) => setTimeframe(e.target.value)} disabled={loading} />
            </Field>
            <Field label="In-sample ratio" hint="default 0.70">
              <input className="tv-input font-mono" value={inSampleRatio} onChange={(e) => setInSampleRatio(e.target.value)} disabled={loading} />
            </Field>
            <Field label="Range start">
              <input type="date" className="tv-input" value={rangeStart} onChange={(e) => setRangeStart(e.target.value)} required disabled={loading} />
            </Field>
            <Field label="Range end">
              <input type="date" className="tv-input" value={rangeEnd} onChange={(e) => setRangeEnd(e.target.value)} required disabled={loading} />
            </Field>
            <Field label="Initial capital">
              <input className="tv-input font-mono" value={initialCapital} onChange={(e) => setInitialCapital(e.target.value)} disabled={loading} />
            </Field>
            <Field label="Window size (days)">
              <input type="number" min={1} className="tv-input font-mono" value={windowSize} onChange={(e) => setWindowSize(e.target.value)} required disabled={loading} />
            </Field>
            <Field label="Step size (days)">
              <input type="number" min={1} className="tv-input font-mono" value={stepSize} onChange={(e) => setStepSize(e.target.value)} required disabled={loading} />
            </Field>
          </div>
          <SyncResearchWarning />
          <ResearchActions loading={loading} onReset={reset} hasResult={!!data} />
        </form>
      </Card>

      {error && (
        <Alert tone="error" code={error.code} onRetry={() => submit()}>
          {error.message}
        </Alert>
      )}

      {timedOut && !data && (
        <Alert tone="warning" title="Client timeout reached">
          The client stopped waiting after 120s. The server may still be
          computing. Retry once ready.
        </Alert>
      )}

      {data && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard label="Total windows" value={fmtDecimal(data.total_windows, 0)} />
            <StatCard label="Included windows" value={fmtDecimal(data.included_window_count, 0)} />
            <StatCard label="Excluded windows" value={fmtDecimal(data.excluded_window_count, 0)} hint="Below MIN_TRADES_FOR_DISTRIBUTION=2 OOS trades" />
            <StatCard label="In-sample ratio" value={data.in_sample_ratio} />
          </div>

          <Card title="OOS expectancy per window" description="distribution.windows[].out_of_sample_expectancy">
            {windowBars.length === 0 ? (
              <EmptyState title="No windows" description="No included windows in this run." />
            ) : (
              <BarChartTV
                data={windowBars}
                height={260}
                yTickFormatter={(v) => `₹${v.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`}
                tooltipFormatter={(v) => `₹${v.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`}
              />
            )}
          </Card>

          <Card title="OOS distribution" description="min / max / median / count_positive">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <DistributionPanel label="OOS expectancy" entry={data.distribution.out_of_sample_expectancy} format="inr" />
              <DistributionPanel label="OOS Sharpe ratio" entry={data.distribution.out_of_sample_sharpe_ratio} format="ratio" />
              <DistributionPanel label="OOS win rate" entry={data.distribution.out_of_sample_win_rate} format="pct" />
            </div>
          </Card>

          <Card title="Per-window detail" description={`${data.windows.length} window(s)`}>
            <div className="overflow-x-auto tv-scrollbar">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-xs text-slate-500">
                    {["#", "Range", "IS trades", "OOS trades", "IS expectancy", "OOS expectancy", "OOS Sharpe", "OOS win rate", "Status"].map((h) => (
                      <th key={h} className="px-3 py-2 text-left font-semibold">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.windows.map((w) => (
                    <tr key={w.window_index} className="border-b border-slate-100">
                      <td className="px-3 py-2">W{w.window_index + 1}</td>
                      <td className="px-3 py-2 text-xs">{w.range_start.slice(0, 10)} → {w.range_end.slice(0, 10)}</td>
                      <td className="px-3 py-2 font-mono text-right tabular-nums">{fmtDecimal(w.in_sample_trade_count, 0)}</td>
                      <td className="px-3 py-2 font-mono text-right tabular-nums">{fmtDecimal(w.out_of_sample_trade_count, 0)}</td>
                      <td className="px-3 py-2 font-mono text-right tabular-nums">₹{fmtDecimal(w.in_sample_expectancy)}</td>
                      <td className="px-3 py-2 font-mono text-right tabular-nums">₹{fmtDecimal(w.out_of_sample_expectancy)}</td>
                      <td className="px-3 py-2 font-mono text-right tabular-nums">{fmtRatio(w.out_of_sample_sharpe_ratio)}</td>
                      <td className="px-3 py-2 font-mono text-right tabular-nums">{fmtPct(w.out_of_sample_win_rate)}</td>
                      <td className="px-3 py-2"><Chip tone={w.status === "COMPLETED" ? "emerald" : w.status === "FAILED" ? "rose" : "amber"}>{w.status}</Chip></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

function DistributionPanel({
  label,
  entry,
  format,
}: {
  label: string;
  entry: WalkForwardDistributionEntry;
  format: "inr" | "pct" | "ratio";
}) {
  const fmt = (v: string | null) => {
    if (v === null) return "--";
    if (format === "inr") return `₹${fmtDecimal(v)}`;
    if (format === "pct") return fmtPct(v);
    return fmtRatio(v);
  };
  const positivePct = entry.count > 0 ? (entry.count_positive / entry.count) * 100 : 0;
  return (
    <div className="border border-slate-200 rounded-md p-3">
      <div className="text-xs font-semibold text-slate-700 mb-2">{label}</div>
      <dl className="grid grid-cols-2 gap-2 text-xs">
        <KV k="Count" v={fmtDecimal(entry.count, 0)} />
        <KV k="Positive" v={`${fmtDecimal(entry.count_positive, 0)} (${fmtDecimal(positivePct, 1)}%)`} />
        <KV k="Min" v={fmt(entry.min)} />
        <KV k="Max" v={fmt(entry.max)} />
        <KV k="Median" v={fmt(entry.median)} />
      </dl>
    </div>
  );
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div>
      <dt className="text-slate-500">{k}</dt>
      <dd className="font-mono tabular-nums text-slate-900">{v}</dd>
    </div>
  );
}
