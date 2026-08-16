// Edge Validation page — POST /backtesting/edge-validation/.
// Per 04_API_CONTRACT.md: VERIFIED request + response shape.
// Renders: rule × cost-level matrix (baseline_has_edge vs realistic_cost_has_edge + flipped),
// edge_criterion panel, per-rule drill-down.

import { useState, type FormEvent } from "react";
import { Card } from "@/components/Card";
import { Alert } from "@/components/Alert";
import { Chip, hasEdgeTone } from "@/components/Chip";
import { EmptyState } from "@/components/EmptyState";
import { Field, ResearchActions, SyncResearchWarning, useSyncResearch } from "./_research-utils";
import { runEdgeValidation } from "@/api/research";
import { toIso, todayDate } from "@/lib/time";
import { fmtDecimal, fmtPct, fmtRatio, toNum } from "@/lib/decimal";
import type {
  EdgeValidationRequest,
  EdgeValidationResponse,
  EdgeRuleReport,
  EdgeCriterion,
} from "@/types/research";

export function EdgeValidation() {
  const [symbol, setSymbol] = useState("RELIANCE");
  const [timeframe, setTimeframe] = useState("15min");
  const [rangeStart, setRangeStart] = useState(todayDate());
  const [rangeEnd, setRangeEnd] = useState(todayDate());
  const [windowSize, setWindowSize] = useState("30");
  const [stepSize, setStepSize] = useState("10");
  const [inSampleRatio, setInSampleRatio] = useState("0.70");
  const [commissionRate, setCommissionRate] = useState("0.0003");
  const [slippageBps, setSlippageBps] = useState("5.0");
  const [initialCapital, setInitialCapital] = useState("1000000");

  const buildRequest = (): EdgeValidationRequest => ({
    symbol: symbol.toUpperCase(),
    timeframe: timeframe || undefined,
    range_start: toIso(rangeStart, "00:00"),
    range_end: toIso(rangeEnd, "23:59"),
    window_size_days: Number(windowSize),
    step_size_days: Number(stepSize),
    in_sample_ratio: inSampleRatio || undefined,
    realistic_commission_rate: commissionRate || undefined,
    realistic_slippage_bps: slippageBps || undefined,
    initial_capital: initialCapital || undefined,
  });

  const { loading, data, error, timedOut, submit, reset } =
    useSyncResearch<EdgeValidationResponse>(() => runEdgeValidation(buildRequest()));

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (loading) return;
    submit();
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Edge Validation</h1>
        <p className="text-sm text-slate-500 mt-1">
          Per-rule empirical edge at two cost levels: baseline (zero cost) vs realistic cost.
        </p>
      </div>

      <Card title="Configuration" description="POST /backtesting/edge-validation/">
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Field label="Symbol">
              <input className="tv-input" value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} required disabled={loading} />
            </Field>
            <Field label="Timeframe" hint="optional">
              <input className="tv-input" value={timeframe} onChange={(e) => setTimeframe(e.target.value)} disabled={loading} />
            </Field>
            <Field label="In-sample ratio">
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
            <Field label="Realistic commission rate" hint="default 0.0003">
              <input className="tv-input font-mono" value={commissionRate} onChange={(e) => setCommissionRate(e.target.value)} disabled={loading} />
            </Field>
            <Field label="Realistic slippage (bps)" hint="default 5.0">
              <input className="tv-input font-mono" value={slippageBps} onChange={(e) => setSlippageBps(e.target.value)} disabled={loading} />
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
          <Card title="Edge criterion" description="EDGE_CRITERION — rendered as returned">
            <EdgeCriterionPanel c={data.edge_criterion} />
          </Card>

          <Card title="Cost-level parameters">
            <dl className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
              <KV k="Realistic commission rate" v={data.realistic_commission_rate} />
              <KV k="Realistic slippage (bps)" v={data.realistic_slippage_bps} />
              <KV k="In-sample ratio" v={data.in_sample_ratio} />
              <KV k="Window / step (days)" v={`${data.window_size_days} / ${data.step_size_days}`} />
            </dl>
          </Card>

          <Card title="Rule × cost-level matrix" description="by_rule[*]: baseline_has_edge vs realistic_cost_has_edge (+ flipped)">
            {Object.keys(data.by_rule).length === 0 ? (
              <EmptyState title="No rule results" description="Edge validation returned no per-rule buckets." />
            ) : (
              <div className="overflow-x-auto tv-scrollbar">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-xs text-slate-500">
                      <th className="px-3 py-2 text-left font-semibold">Rule</th>
                      <th className="px-3 py-2 text-center font-semibold">Baseline (0 cost)</th>
                      <th className="px-3 py-2 text-center font-semibold">Realistic cost</th>
                      <th className="px-3 py-2 text-center font-semibold">Flipped</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(data.by_rule).map(([rid, e]) => (
                      <tr key={rid} className="border-b border-slate-100">
                        <td className="px-3 py-2"><Chip tone="violet">{rid}</Chip></td>
                        <td className="px-3 py-2 text-center"><HasEdgeChip v={e.baseline_has_edge} /></td>
                        <td className="px-3 py-2 text-center"><HasEdgeChip v={e.realistic_cost_has_edge} /></td>
                        <td className="px-3 py-2 text-center">
                          {e.flipped ? (
                            <Chip tone="amber">flipped</Chip>
                          ) : (
                            <span className="text-slate-400 text-xs">—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card title="Per-rule drill-down" description="by_rule[*].baseline.by_rule + realistic_cost.by_rule">
            <PerRuleDrilldown data={data} />
          </Card>
        </div>
      )}
    </div>
  );
}

function HasEdgeChip({ v }: { v: boolean | null }) {
  if (v === true) return <Chip tone="emerald">has_edge</Chip>;
  if (v === false) return <Chip tone="rose">no_edge</Chip>;
  return <Chip tone="amber">insufficient</Chip>;
}

function EdgeCriterionPanel({ c }: { c: EdgeCriterion }) {
  return (
    <dl className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
      <KV k="expectancy_greater_than_zero" v={String(c.expectancy_greater_than_zero)} />
      <KV k="profit_factor_not_none" v={String(c.profit_factor_not_none)} />
      <KV k="profit_factor_greater_than_one" v={c.profit_factor_greater_than_one} />
      <KV k="min_trades" v={String(c.min_trades)} />
      <div className="md:col-span-2">
        <dt className="text-slate-500">insufficient_data</dt>
        <dd className="text-slate-700">{c.insufficient_data}</dd>
      </div>
    </dl>
  );
}

function PerRuleDrilldown({ data }: { data: EdgeValidationResponse }) {
  // Extract per-rule reports from baseline.by_rule and realistic_cost.by_rule.
  const baselineByRule = data.baseline.by_rule || {};
  const realisticByRule = data.realistic_cost.by_rule || {};
  const ruleIds = Array.from(new Set([...Object.keys(baselineByRule), ...Object.keys(realisticByRule)]));
  if (ruleIds.length === 0) {
    return <EmptyState title="No per-rule reports" description="Embedded by_rule dicts are empty." />;
  }
  return (
    <div className="space-y-4">
      {(["baseline", "realistic_cost"] as const).map((level) => {
        const byRule = level === "baseline" ? baselineByRule : realisticByRule;
        const report = level === "baseline" ? data.baseline : data.realistic_cost;
        return (
          <div key={level} className="border border-slate-200 rounded-md p-3">
            <div className="text-xs font-semibold text-slate-700 mb-2 flex items-center gap-2">
              <span>{level === "baseline" ? "Baseline (0 cost)" : "Realistic cost"}</span>
              <span className="text-slate-400">·</span>
              <span className="font-mono">{report.commission_rate} commission / {report.slippage_bps} bps slippage</span>
            </div>
            <div className="overflow-x-auto tv-scrollbar">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-xs text-slate-500">
                    {["Rule", "Trades", "Win rate", "Expectancy", "PF", "Sharpe", "Sortino", "Max DD %", "Has edge"].map((h) => (
                      <th key={h} className="px-3 py-2 text-left font-semibold">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {ruleIds.map((rid) => {
                    const r = byRule[rid] as EdgeRuleReport | undefined;
                    if (!r) {
                      return (
                        <tr key={rid} className="border-b border-slate-100">
                          <td colSpan={9} className="px-3 py-2 text-xs text-slate-400 italic">
                            {rid}: no report at {level}
                          </td>
                        </tr>
                      );
                    }
                    return (
                      <tr key={rid} className="border-b border-slate-100">
                        <td className="px-3 py-2"><Chip tone="violet">{r.rule_id}</Chip></td>
                        <td className="px-3 py-2 font-mono text-right tabular-nums">{fmtDecimal(r.trade_count, 0)}</td>
                        <td className="px-3 py-2 font-mono text-right tabular-nums">{fmtPct(r.win_rate)}</td>
                        <td className="px-3 py-2 font-mono text-right tabular-nums">₹{fmtDecimal(r.expectancy)}</td>
                        <td className="px-3 py-2 font-mono text-right tabular-nums">{fmtRatio(r.profit_factor)}</td>
                        <td className="px-3 py-2 font-mono text-right tabular-nums">{fmtRatio(r.sharpe_ratio)}</td>
                        <td className="px-3 py-2 font-mono text-right tabular-nums">{fmtRatio(r.sortino_ratio)}</td>
                        <td className="px-3 py-2 font-mono text-right tabular-nums">{fmtPct(r.max_drawdown_pct)}</td>
                        <td className="px-3 py-2 text-center"><HasEdgeChip v={r.has_edge} /></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
      {/* Hint about has_edge tone */}
      <div className="text-[11px] text-slate-500 italic">
        has_edge tone: <span className="text-emerald-700">emerald = true</span> ·
        <span className="text-rose-700"> rose = false</span> ·
        <span className="text-amber-700"> amber = null (insufficient data — never treated as False)</span>
      </div>
      {/* silence unused import */}
      <span hidden>{String(typeof hasEdgeTone)}</span>
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

// silence unused
void toNum;
