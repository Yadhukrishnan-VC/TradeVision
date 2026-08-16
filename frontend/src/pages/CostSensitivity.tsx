// Cost Sensitivity page — POST /backtesting/cost-sensitivity/.
// Per 04_API_CONTRACT.md: VERIFIED request + response shape.
// Renders: per-rule expectancy-vs-cost line chart with breakeven markers,
// classification badges per rule (BREAKEVEN_FOUND / NEVER_PROFITABLE / SURVIVES_FULL_RANGE).

import { useMemo, useState, type FormEvent } from "react";
import { Card } from "@/components/Card";
import { Alert } from "@/components/Alert";
import { Chip, classificationTone } from "@/components/Chip";
import { EmptyState } from "@/components/EmptyState";
import { LineChartTV } from "@/components/charts";
import { Field, ResearchActions, SyncResearchWarning, useSyncResearch } from "./_research-utils";
import { runCostSensitivity } from "@/api/research";
import { toIso, todayDate } from "@/lib/time";
import { fmtDecimal, toNum } from "@/lib/decimal";
import type {
  CostSensitivityRequest,
  CostSensitivityResponse,
  CostSensitivityByRule,
} from "@/types/research";

export function CostSensitivity() {
  const [symbol, setSymbol] = useState("RELIANCE");
  const [timeframe, setTimeframe] = useState("15min");
  const [rangeStart, setRangeStart] = useState(todayDate());
  const [rangeEnd, setRangeEnd] = useState(todayDate());
  const [commissionStart, setCommissionStart] = useState("0");
  const [commissionEnd, setCommissionEnd] = useState("0.001");
  const [commissionStep, setCommissionStep] = useState("0.0002");
  const [slippageStart, setSlippageStart] = useState("0");
  const [slippageEnd, setSlippageEnd] = useState("10");
  const [slippageStep, setSlippageStep] = useState("2");
  const [initialCapital, setInitialCapital] = useState("1000000");

  const buildRequest = (): CostSensitivityRequest => ({
    symbol: symbol.toUpperCase(),
    timeframe: timeframe || undefined,
    range_start: toIso(rangeStart, "00:00"),
    range_end: toIso(rangeEnd, "23:59"),
    commission_start: commissionStart,
    commission_end: commissionEnd,
    commission_step: commissionStep,
    slippage_start: slippageStart,
    slippage_end: slippageEnd,
    slippage_step: slippageStep,
    initial_capital: initialCapital || undefined,
  });

  const { loading, data, error, timedOut, submit, reset } =
    useSyncResearch<CostSensitivityResponse>(() => runCostSensitivity(buildRequest()));

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (loading) return;
    submit();
  }

  // Convert each rule's series[] into a chart-ready {x: cost_level, y: expectancy}.
  // Use the index of the series since cost_level is a composite label (commission×slippage).
  const ruleCharts = useMemo(() => {
    if (!data?.by_rule) return [];
    return Object.entries(data.by_rule).map(([rid, r]) => {
      const series = (r.series || []).map((p, i) => ({
        x: i,
        y: toNum(p.expectancy),
      }));
      return { rid, rule: r, series };
    });
  }, [data]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Cost Sensitivity</h1>
        <p className="text-sm text-slate-500 mt-1">
          Commission × slippage grid sweep. Per-rule breakeven detection and survivability classification.
        </p>
      </div>

      <Card title="Configuration" description="POST /backtesting/cost-sensitivity/ (max 50 grid points)">
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Field label="Symbol">
              <input className="tv-input" value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} required disabled={loading} />
            </Field>
            <Field label="Timeframe" hint="optional">
              <input className="tv-input" value={timeframe} onChange={(e) => setTimeframe(e.target.value)} disabled={loading} />
            </Field>
            <Field label="Initial capital">
              <input className="tv-input font-mono" value={initialCapital} onChange={(e) => setInitialCapital(e.target.value)} disabled={loading} />
            </Field>
            <Field label="Range start">
              <input type="date" className="tv-input" value={rangeStart} onChange={(e) => setRangeStart(e.target.value)} required disabled={loading} />
            </Field>
            <Field label="Range end">
              <input type="date" className="tv-input" value={rangeEnd} onChange={(e) => setRangeEnd(e.target.value)} required disabled={loading} />
            </Field>
            <div className="md:col-span-3 grid grid-cols-3 gap-2 text-xs text-slate-500">
              <div>Commission (start / end / step)</div>
              <div>Slippage (start / end / step)</div>
              <div></div>
            </div>
            <Field label="Commission start">
              <input className="tv-input font-mono" value={commissionStart} onChange={(e) => setCommissionStart(e.target.value)} required disabled={loading} />
            </Field>
            <Field label="Commission end">
              <input className="tv-input font-mono" value={commissionEnd} onChange={(e) => setCommissionEnd(e.target.value)} required disabled={loading} />
            </Field>
            <Field label="Commission step">
              <input className="tv-input font-mono" value={commissionStep} onChange={(e) => setCommissionStep(e.target.value)} required disabled={loading} />
            </Field>
            <Field label="Slippage start (bps)">
              <input className="tv-input font-mono" value={slippageStart} onChange={(e) => setSlippageStart(e.target.value)} required disabled={loading} />
            </Field>
            <Field label="Slippage end (bps)">
              <input className="tv-input font-mono" value={slippageEnd} onChange={(e) => setSlippageEnd(e.target.value)} required disabled={loading} />
            </Field>
            <Field label="Slippage step (bps)">
              <input className="tv-input font-mono" value={slippageStep} onChange={(e) => setSlippageStep(e.target.value)} required disabled={loading} />
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
          The client stopped waiting after 120s. Retry once ready.
        </Alert>
      )}

      {data && (
        <div className="space-y-4">
          <Card title="Grid summary">
            <div className="text-sm text-slate-600">
              <span className="font-medium text-slate-900">{data.grid_points_run}</span> grid points run.
            </div>
          </Card>

          <Card title="Classification summary" description="by_rule[*].classification">
            {Object.keys(data.by_rule).length === 0 ? (
              <EmptyState title="No rules" description="No per-rule results in this sweep." />
            ) : (
              <div className="overflow-x-auto tv-scrollbar">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-xs text-slate-500">
                      {["Rule", "Expectancy @ min", "Expectancy @ max", "Breakeven commission", "Breakeven slippage (bps)", "Classification"].map((h) => (
                        <th key={h} className="px-3 py-2 text-left font-semibold">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(data.by_rule).map(([rid, r]) => (
                      <tr key={rid} className="border-b border-slate-100">
                        <td className="px-3 py-2"><Chip tone="violet">{r.rule_id}</Chip></td>
                        <td className="px-3 py-2 font-mono text-right tabular-nums">₹{fmtDecimal(r.expectancy_at_min_cost)}</td>
                        <td className="px-3 py-2 font-mono text-right tabular-nums">₹{fmtDecimal(r.expectancy_at_max_cost)}</td>
                        <td className="px-3 py-2 font-mono text-right tabular-nums">{r.breakeven_commission_rate === null ? "--" : r.breakeven_commission_rate}</td>
                        <td className="px-3 py-2 font-mono text-right tabular-nums">{r.breakeven_slippage_bps === null ? "--" : r.breakeven_slippage_bps}</td>
                        <td className="px-3 py-2"><Chip tone={classificationTone(r.classification)}>{r.classification}</Chip></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card title="Per-rule expectancy vs cost" description="by_rule[*].series[] — line per rule with breakeven marker">
            {ruleCharts.length === 0 ? (
              <EmptyState title="No series" description="No per-rule series to plot." />
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {ruleCharts.map(({ rid, rule, series }) => (
                  <RuleChart key={rid} rid={rid} rule={rule} series={series} />
                ))}
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}

function RuleChart({
  rid,
  rule,
  series,
}: {
  rid: string;
  rule: CostSensitivityByRule;
  series: Array<{ x: number; y: number | null }>;
}) {
  // Find breakeven index — the first x where y crosses 0. Used for marker.
  let breakevenX: number | null = null;
  for (let i = 1; i < series.length; i++) {
    const prev = series[i - 1].y;
    const cur = series[i].y;
    if (prev !== null && cur !== null && prev > 0 && cur <= 0) {
      breakevenX = series[i].x;
      break;
    }
    if (prev !== null && cur !== null && prev < 0 && cur >= 0) {
      breakevenX = series[i].x;
      break;
    }
  }
  // For SURVIVES_FULL_RANGE, the breakeven_* is the tested max (per 07). Mark it.
  if (breakevenX === null && rule.classification === "SURVIVES_FULL_RANGE") {
    breakevenX = rule.breakeven_commission_rate !== null ? series.length - 1 : null;
  }
  return (
    <div className="border border-slate-200 rounded-md p-3">
      <div className="flex items-center justify-between mb-2 gap-2">
        <Chip tone="violet">{rid}</Chip>
        <Chip tone={classificationTone(rule.classification)}>{rule.classification}</Chip>
      </div>
      <LineChartTV
        data={series}
        height={180}
        xLabel="cost level (index)"
        yLabel="expectancy (₹)"
        breakevenX={breakevenX}
        breakevenLabel={
          rule.classification === "BREAKEVEN_FOUND"
            ? "Breakeven"
            : rule.classification === "SURVIVES_FULL_RANGE"
            ? "Survivability floor"
            : "Breakeven"
        }
        yTickFormatter={(v) => `₹${v.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`}
        tooltipFormatter={(v) => `₹${v.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`}
      />
      {rule.classification === "NEVER_PROFITABLE" && (
        <p className="text-[11px] text-rose-700 mt-2">
          Negative at every tested level. Breakeven is null — do not fabricate a zero or extrapolation.
        </p>
      )}
      {rule.classification === "SURVIVES_FULL_RANGE" && (
        <p className="text-[11px] text-emerald-700 mt-2">
          Positive through the tested range. Breakeven value is the tested maximum, treated as an honest survivability floor.
        </p>
      )}
    </div>
  );
}
