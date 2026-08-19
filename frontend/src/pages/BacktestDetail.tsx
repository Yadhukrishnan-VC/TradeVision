// BacktestDetail — Phase 2 centerpiece.
// Polls GET /backtesting/runs/:id/ until COMPLETED/FAILED, then renders the
// full run_stats dashboard: equity curve (cumulative from trades[].net_pnl),
// IS/OOS equity curves, by_regime bars, by_rule horizontal bars, trades table,
// max_drawdown_pct as a StatCard (NOT a chart — gap P4), key metrics.

import { useEffect, useMemo } from "react";
import { useParams, Link } from "react-router-dom";
import { Breadcrumbs } from "@/components/Breadcrumbs";
import { Card } from "@/components/Card";
import { StatCard } from "@/components/StatCard";
import { Chip, runStatusTone, regimeTone } from "@/components/Chip";
import { Alert } from "@/components/Alert";
import { Spinner } from "@/components/Spinner";
import { DataTable, type Column } from "@/components/DataTable";
import { Tabs, type TabDef } from "@/components/Tabs";
import { EquityCurve, BarChartTV, Histogram as HistogramLocal } from "@/components/charts";
import { usePoll } from "@/hooks/usePoll";
import { getBacktestRun } from "@/api/research";
import type { BacktestRunDetail, BacktestTrade, RunStats } from "@/types/research";
import { updateRecentRunStatus } from "@/lib/recentRuns";
import { fmtDate, fmtDateTime } from "@/lib/time";
import {
  fmtDecimal,
  fmtInr,
  fmtPct,
  fmtRatio,
  fmtInt,
  pnlColor,
  toNum,
} from "@/lib/decimal";

export function BacktestDetail() {
  const { id } = useParams<{ id: string }>();
  if (!id) return <Alert tone="error">Missing run id.</Alert>;

  const { data, error, setData } = usePoll<BacktestRunDetail>(
    () => getBacktestRun(id),
    [id],
    {
      shouldStop: (d) => d?.status === "COMPLETED" || d?.status === "FAILED",
      intervalMs: 2000,
      timeoutMs: 5 * 60 * 1000,
    }
  );

  // Sync status back to recent-runs store so the list page reflects completion.
  useEffect(() => {
    if (data?.status) updateRecentRunStatus(id, data.status);
  }, [data?.status, id]);

  const run = data;
  const stats: RunStats | null = run?.stats ?? null;

  // Cumulative equity curve from trades[].net_pnl.
  const equitySeries = useMemo(() => {
    if (!stats?.trades || stats.trades.length === 0) return [];
    let cum = toNum(stats.available_capital) ?? toNum(stats.equity_at_completion) ?? 0;
    return stats.trades.map((t, i) => {
      const v = toNum(t.net_pnl);
      if (v !== null) cum += v;
      return { label: `#${i + 1}`, value: cum };
    });
  }, [stats]);

  // IS / OOS equity arrays (per-bucket equity_curve per 06_CHARTS.md).
  const isEquityDecimals = stats?.in_sample?.equity_curve;
  const oosEquityDecimals = stats?.out_of_sample?.equity_curve;

  // Regime breakdown bars.
  const regimeBars = useMemo(() => {
    if (!stats?.by_regime) return [];
    return Object.entries(stats.by_regime).map(([regime, b]) => ({
      label: regime,
      value: toNum(b.net_pnl),
      tone: (toNum(b.net_pnl) ?? 0) >= 0 ? "#10b981" : "#ef4444",
    }));
  }, [stats]);

  // Rule attribution horizontal bars.
  const ruleBars = useMemo(() => {
    if (!stats?.by_rule) return [];
    const arr = Object.entries(stats.by_rule).map(([rid, b]) => ({
      label: rid,
      value: toNum(b.expectancy),
      tone: (toNum(b.expectancy) ?? 0) >= 0 ? "#10b981" : "#ef4444",
    }));
    if ((stats.unattributed_trade_count ?? 0) > 0) {
      arr.push({ label: "unattributed", value: 0, tone: "#94a3b8" });
    }
    return arr;
  }, [stats]);

  // Trade table columns.
  const tradeColumns: Column<BacktestTrade>[] = [
    {
      key: "order_id",
      header: "Order ID",
      cell: (r) => <code className="text-xs">{r.order_id.slice(0, 8)}</code>,
    },
    { key: "symbol", header: "Symbol", cell: (r) => r.symbol },
    {
      key: "side",
      header: "Side",
      cell: (r) => (
        <Chip tone={r.side === "LONG" ? "emerald" : "rose"}>{r.side}</Chip>
      ),
    },
    {
      key: "quantity",
      header: "Qty",
      numeric: true,
      cell: (r) => fmtDecimal(r.quantity, 0),
      sortAccessor: (r) => toNum(r.quantity),
    },
    {
      key: "entry_price",
      header: "Entry",
      numeric: true,
      cell: (r) => fmtDecimal(r.entry_price),
      sortAccessor: (r) => toNum(r.entry_price),
    },
    {
      key: "avg_fill_price",
      header: "Fill",
      numeric: true,
      cell: (r) => fmtDecimal(r.avg_fill_price),
      sortAccessor: (r) => toNum(r.avg_fill_price),
    },
    {
      key: "net_pnl",
      header: "Net PnL",
      numeric: true,
      cell: (r) => (
        <span className={pnlColor(r.net_pnl)}>{fmtInr(r.net_pnl)}</span>
      ),
      sortAccessor: (r) => toNum(r.net_pnl),
    },
    {
      key: "created_at",
      header: "Time",
      cell: (r) => fmtDateTime(r.created_at),
      sortAccessor: (r) => r.created_at,
    },
  ];

  // Polling in progress, no data yet.
  if (!run && !error) {
    return (
      <div className="space-y-4">
        <Breadcrumbs
          items={[
            { label: "Research", to: "/research/backtests" },
            { label: "Backtests", to: "/research/backtests" },
            { label: id.slice(0, 8) },
          ]}
        />
        <Card title="Loading backtest run…">
          <div className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400 py-6 justify-center">
            <Spinner /> Fetching run status…
          </div>
        </Card>
      </div>
    );
  }

  if (error && !run) {
    return (
      <div className="space-y-4">
        <Breadcrumbs
          items={[
            { label: "Research", to: "/research/backtests" },
            { label: "Backtests", to: "/research/backtests" },
            { label: id.slice(0, 8) },
          ]}
        />
        <Alert tone="error" code={error.code}>
          {error.message || "Failed to load backtest run."}
        </Alert>
        <Link to="/research/backtests" className="text-sm text-indigo-600 underline">
          ← Back to backtests
        </Link>
      </div>
    );
  }

  const status = run?.status;
  const failure = run?.failure_reason;

  const tabs: TabDef[] = [
    {
      key: "overview",
      label: "Overview",
      content: (
        <div className="space-y-4">
          {/* Run metadata */}
          <Card title="Run metadata">
            <dl className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
              <Meta label="Run ID" value={<code className="text-xs">{run?.run_id}</code>} />
              <Meta label="Account ID" value={<code className="text-xs">{run?.account_id}</code>} />
              <Meta label="Symbol" value={run?.symbol} />
              <Meta label="Timeframe" value={run?.timeframe || "—"} />
              <Meta label="Range start" value={fmtDate(run?.range_start)} />
              <Meta label="Range end" value={fmtDate(run?.range_end)} />
              <Meta label="Started at" value={fmtDateTime(run?.started_at)} />
              <Meta label="Completed at" value={fmtDateTime(run?.completed_at)} />
              <Meta label="Status" value={<Chip tone={runStatusTone(status)}>{status}</Chip>} />
            </dl>
          </Card>

          {status === "FAILED" && failure && (
            <Alert tone="error" title="Backtest failed" code="backtest_failed">
              {failure}
            </Alert>
          )}

          {status === "PENDING" || status === "RUNNING" ? (
            <Card title="In progress">
              <div className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400 py-4">
                <Spinner />
                <span>Run is {status}. Polling for updates…</span>
              </div>
              <div className="text-xs text-slate-500 dark:text-slate-400">
                Status checks every 2s. Polling will stop when COMPLETED or FAILED.
              </div>
            </Card>
          ) : null}

          {stats && (
            <>
              {/* Key metrics row */}
              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
                <StatCard label="Net PnL" value={fmtInr(stats.net_pnl)} delta={pnlColor(stats.net_pnl) === "text-emerald-600" ? "profit" : pnlColor(stats.net_pnl) === "text-rose-600" ? "loss" : undefined} deltaDirection={pnlColor(stats.net_pnl) === "text-emerald-600" ? "up" : "down"} />
                <StatCard label="Expectancy" value={fmtInr(stats.expectancy)} />
                <StatCard label="Win rate" value={fmtPct(stats.win_rate)} />
                <StatCard label="Profit factor" value={fmtRatio(stats.profit_factor)} />
                <StatCard label="Trades" value={fmtInt(stats.trade_count)} />
                <StatCard label="Max DD %" value={fmtPct(stats.max_drawdown_pct)} />
              </div>

              {/* Equity curve (merged, cumulative from trades[].net_pnl) */}
              <Card title="Equity curve" description="Cumulative net PnL from stats.trades[].net_pnl + available_capital">
                <EquityCurve series={equitySeries} />
              </Card>

              {/* IS / OOS equity curves (per 06_CHARTS.md — bucket equity_curve arrays) */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <Card title="In-sample equity" description="stats.in_sample.equity_curve">
                  <EquityCurve decimals={isEquityDecimals} height={180} lineOnly />
                </Card>
                <Card title="Out-of-sample equity" description="stats.out_of_sample.equity_curve">
                  <EquityCurve decimals={oosEquityDecimals} height={180} lineOnly />
                </Card>
              </div>

              {/* Regime + Rule attribution */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <Card title="PnL by regime" description="stats.by_regime[*].net_pnl">
                  <BarChartTV data={regimeBars} height={220} yTickFormatter={(v) => fmtInr(v)} tooltipFormatter={(v) => fmtInr(v)} />
                </Card>
                <Card title="Expectancy by rule" description="stats.by_rule[*].expectancy">
                  <BarChartTV data={ruleBars} layout="vertical" height={220} yTickFormatter={(v) => fmtInr(v)} tooltipFormatter={(v) => fmtInr(v)} />
                </Card>
              </div>

              {/* Extended metrics */}
              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
                <StatCard label="Sharpe" value={fmtRatio(stats.sharpe_ratio)} />
                <StatCard label="Sortino" value={fmtRatio(stats.sortino_ratio)} />
                <StatCard label="Benchmark return" value={fmtPct(stats.benchmark_return_pct)} />
                <StatCard label="Gross profit" value={fmtInr(stats.gross_profit)} />
                <StatCard label="Gross loss" value={fmtInr(stats.gross_loss)} />
                <StatCard label="Equity at completion" value={fmtInr(stats.equity_at_completion)} />
                <StatCard label="Available capital" value={fmtInr(stats.available_capital)} />
                <StatCard label="Win count" value={fmtInt(stats.win_count)} />
                <StatCard label="Loss count" value={fmtInt(stats.loss_count)} />
                <StatCard label="Fill count" value={fmtInt(stats.fill_count)} />
                <StatCard label="Risk rejected" value={fmtInt(stats.risk_rejected_count)} />
                <StatCard label="Transaction costs" value={fmtInr(stats.total_transaction_costs)} />
                <StatCard label="Slippage impact" value={fmtInr(stats.total_slippage_impact)} />
                <StatCard label="Unattributed trades" value={fmtInt(stats.unattributed_trade_count)} />
                <StatCard label="Missing regime" value={fmtInt(stats.missing_regime_count)} />
              </div>

              {/* Trades table */}
              <Card title="Trades" description={`${stats.trades.length} trade(s)`}>
                <DataTable
                  columns={tradeColumns}
                  rows={stats.trades}
                  rowKey={(r) => r.order_id}
                  initialSortKey="created_at"
                  initialSortDir="asc"
                  emptyTitle="No trades in this run"
                />
              </Card>
            </>
          )}
        </div>
      ),
    },
    {
      key: "by_regime",
      label: "By Regime",
      content: stats ? <ByRegimeTab stats={stats} /> : <Spinner />,
    },
    {
      key: "by_rule",
      label: "By Rule",
      content: stats ? <ByRuleTab stats={stats} /> : <Spinner />,
    },
    {
      key: "is_oos",
      label: "IS / OOS",
      content: stats ? <IsOosTab stats={stats} /> : <Spinner />,
    },
  ];

  return (
    <div className="space-y-4">
      <Breadcrumbs
        items={[
          { label: "Research", to: "/research/backtests" },
          { label: "Backtests", to: "/research/backtests" },
          { label: run?.run_id?.slice(0, 8) || id.slice(0, 8) },
        ]}
      />
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
            Backtest — {run?.symbol}
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            {fmtDate(run?.range_start)} → {fmtDate(run?.range_end)}
            {run?.timeframe ? ` · ${run.timeframe}` : ""}
          </p>
        </div>
        <Chip tone={runStatusTone(status)}>{status}</Chip>
      </div>
      <Tabs tabs={tabs} />
      {/* setData is exported by usePoll but unused here; placeholder. */}
      <span hidden>{String(typeof setData)}</span>
    </div>
  );
}

function Meta({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="text-sm text-slate-900 dark:text-slate-100 mt-0.5">{value || "—"}</dd>
    </div>
  );
}

function ByRegimeTab({ stats }: { stats: RunStats }) {
  const rows = Object.entries(stats.by_regime);
  if (rows.length === 0) return <Alert tone="info">No regime attribution.</Alert>;
  return (
    <Card title="Per-regime buckets" description="stats.by_regime">
      <div className="overflow-x-auto tv-scrollbar">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-800 text-xs text-slate-500 dark:text-slate-400">
              {["Regime", "Trades", "Win rate", "Expectancy", "PF", "Net PnL", "Max DD %"].map((h) => (
                <th key={h} className="px-3 py-2 text-left font-semibold">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(([regime, b]) => (
              <tr key={regime} className="border-b border-slate-100 dark:border-slate-800">
                <td className="px-3 py-2"><Chip tone={regimeTone(regime)}>{regime}</Chip></td>
                <td className="px-3 py-2 font-mono text-right tabular-nums">{fmtInt(b.trade_count)}</td>
                <td className="px-3 py-2 font-mono text-right tabular-nums">{fmtPct(b.win_rate)}</td>
                <td className="px-3 py-2 font-mono text-right tabular-nums">{fmtInr(b.expectancy)}</td>
                <td className="px-3 py-2 font-mono text-right tabular-nums">{fmtRatio(b.profit_factor)}</td>
                <td className={`px-3 py-2 font-mono text-right tabular-nums ${pnlColor(b.net_pnl)}`}>{fmtInr(b.net_pnl)}</td>
                <td className="px-3 py-2 font-mono text-right tabular-nums">{fmtPct(b.max_drawdown_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function ByRuleTab({ stats }: { stats: RunStats }) {
  const rows = Object.entries(stats.by_rule);
  if (rows.length === 0) return <Alert tone="info">No rule attribution.</Alert>;
  return (
    <Card title="Per-rule buckets" description="stats.by_rule">
      <div className="overflow-x-auto tv-scrollbar">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-800 text-xs text-slate-500 dark:text-slate-400">
              {["Rule", "Trades", "Win rate", "Expectancy", "PF", "Net PnL", "Max DD %"].map((h) => (
                <th key={h} className="px-3 py-2 text-left font-semibold">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(([rid, b]) => (
              <tr key={rid} className="border-b border-slate-100 dark:border-slate-800">
                <td className="px-3 py-2"><Chip tone="violet">{rid}</Chip></td>
                <td className="px-3 py-2 font-mono text-right tabular-nums">{fmtInt(b.trade_count)}</td>
                <td className="px-3 py-2 font-mono text-right tabular-nums">{fmtPct(b.win_rate)}</td>
                <td className="px-3 py-2 font-mono text-right tabular-nums">{fmtInr(b.expectancy)}</td>
                <td className="px-3 py-2 font-mono text-right tabular-nums">{fmtRatio(b.profit_factor)}</td>
                <td className={`px-3 py-2 font-mono text-right tabular-nums ${pnlColor(b.net_pnl)}`}>{fmtInr(b.net_pnl)}</td>
                <td className="px-3 py-2 font-mono text-right tabular-nums">{fmtPct(b.max_drawdown_pct)}</td>
              </tr>
            ))}
            {(stats.unattributed_trade_count ?? 0) > 0 && (
              <tr className="border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-950">
                <td className="px-3 py-2"><Chip tone="slate">unattributed</Chip></td>
                <td className="px-3 py-2 font-mono text-right tabular-nums">{fmtInt(stats.unattributed_trade_count)}</td>
                <td colSpan={5} className="px-3 py-2 text-xs text-slate-400 dark:text-slate-500 italic">
                  Trades not attributable to any rule via correlation_id → RuleExecution.analysis_event_id
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function IsOosTab({ stats }: { stats: RunStats }) {
  const isB = stats.in_sample;
  const oosB = stats.out_of_sample;
  return (
    <div className="space-y-4">
      <Card title="In-sample vs Out-of-sample" description="static split by in_sample_ratio">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <BucketPanel label="In-sample" b={isB} />
          <BucketPanel label="Out-of-sample" b={oosB} />
        </div>
      </Card>
      <Card title="Returns distribution" description="bucket.returns arrays (defensive)">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <ReturnsHistogram decimals={isB?.returns} label="In-sample returns" />
          <ReturnsHistogram decimals={oosB?.returns} label="Out-of-sample returns" />
        </div>
      </Card>
    </div>
  );
}

function BucketPanel({ label, b }: { label: string; b: RunStats["in_sample"] }) {
  return (
    <div className="border border-slate-200 dark:border-slate-800 rounded-md p-3">
      <div className="text-xs font-semibold text-slate-700 dark:text-slate-300 mb-2">{label}</div>
      <dl className="grid grid-cols-2 gap-2 text-xs">
        <KV k="Trades" v={fmtInt(b.trade_count)} />
        <KV k="Win rate" v={fmtPct(b.win_rate)} />
        <KV k="Expectancy" v={fmtInr(b.expectancy)} />
        <KV k="Profit factor" v={fmtRatio(b.profit_factor)} />
        <KV k="Sharpe" v={fmtRatio(b.sharpe_ratio)} />
        <KV k="Sortino" v={fmtRatio(b.sortino_ratio)} />
        <KV k="Max DD %" v={fmtPct(b.max_drawdown_pct)} />
        <KV k="Net PnL" v={<span className={pnlColor(b.net_pnl)}>{fmtInr(b.net_pnl)}</span>} />
      </dl>
    </div>
  );
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div>
      <dt className="text-slate-500 dark:text-slate-400">{k}</dt>
      <dd className="font-mono tabular-nums text-slate-900 dark:text-slate-100">{v}</dd>
    </div>
  );
}

function ReturnsHistogram({ decimals, label }: { decimals?: string[]; label: string }) {
  if (!decimals || decimals.length === 0) {
    return (
      <div className="text-xs text-slate-400 dark:text-slate-500 italic">{label}: no returns array.</div>
    );
  }
  // Bin the returns into ~10 buckets between min and max.
  const nums = decimals.map(toNum).filter((n): n is number => n !== null);
  if (nums.length === 0) {
    return <div className="text-xs text-slate-400 dark:text-slate-500 italic">{label}: no parseable returns.</div>;
  }
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  const bins = 10;
  const step = (max - min) / bins || 1;
  const counts = new Array(bins).fill(0);
  for (const n of nums) {
    const idx = Math.min(bins - 1, Math.max(0, Math.floor((n - min) / step)));
    counts[idx]++;
  }
  const data = counts.map((count, i) => ({
    label: `${((min + i * step) * 100).toFixed(1)}%`,
    count,
  }));
  return (
    <div>
      <div className="text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">{label}</div>
      <HistogramLocal data={data} />
    </div>
  );
}

// Local Histogram import (kept here rather than in charts/index.ts barrel
// to avoid pulling the histogram into the equity/bar/line bundle paths).
