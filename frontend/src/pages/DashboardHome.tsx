// DashboardHome — GET /dashboard/home/summary/.
// DashboardHomeSummarySerializer (VERIFIED field set per 04_API_CONTRACT.md).

import { useFetch } from "@/hooks/useFetch";
import { getHomeSummary } from "@/api/dashboard";
import { Card, StatCard, Alert, EmptyState, SkeletonStat } from "@/components";
import { fmtInr, fmtInt, toNum } from "@/lib/decimal";
import { fmtTimeAgo } from "@/lib/time";
import { Link } from "react-router-dom";

export function DashboardHome() {
  const { data, state, error, refetch } = useFetch(getHomeSummary);

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Dashboard</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Live trading-core snapshot · account{" "}
            <code className="text-xs">{data?.account_id?.slice(0, 8) || "—"}</code>
          </p>
        </div>
        {data?.last_updated_at && (
          <span className="text-xs text-slate-400 dark:text-slate-500">Updated {fmtTimeAgo(data.last_updated_at)}</span>
        )}
      </div>

      {state === "loading" && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          {Array.from({ length: 6 }).map((_, i) => <SkeletonStat key={i} />)}
        </div>
      )}

      {state === "error" && error && (
        <Alert tone="error" code={error.code} onRetry={refetch}>
          {error.message}
        </Alert>
      )}

      {state === "empty" && (
        <Card><EmptyState title="No summary available" description="The dashboard returned an empty payload." /></Card>
      )}

      {state === "success" && data && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            <StatCard
              label="Open positions"
              value={fmtInt(data.open_positions_count)}
              hint={<Link to="/positions" className="text-indigo-600 underline">View →</Link>}
            />
            <StatCard
              label="Open orders"
              value={fmtInt(data.open_orders_count)}
              hint={<Link to="/orders" className="text-indigo-600 underline">View →</Link>}
            />
            <StatCard
              label="Today realized PnL"
              value={fmtInr(data.today_realized_pnl)}
              deltaDirection={toNum(data.today_realized_pnl) && toNum(data.today_realized_pnl)! > 0 ? "up" : "down"}
            />
            <StatCard
              label="Today unrealized PnL"
              value={fmtInr(data.today_unrealized_pnl)}
              deltaDirection={toNum(data.today_unrealized_pnl) && toNum(data.today_unrealized_pnl)! > 0 ? "up" : "down"}
            />
            <StatCard label="Active alerts" value={fmtInt(data.active_alerts_count)} />
            <StatCard label="Broker connection" value={data.broker_connection_status || "—"} />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card title="Market session">
              <div className="text-sm">
                <span className="font-medium text-slate-900 dark:text-slate-100">{data.market_session_status || "—"}</span>
                {data.last_updated_at && (
                  <div className="text-xs text-slate-500 dark:text-slate-400 mt-1">Last updated {fmtTimeAgo(data.last_updated_at)}</div>
                )}
              </div>
            </Card>
            <Card title="Quick links">
              <div className="grid grid-cols-2 gap-2 text-sm">
                <Link to="/portfolio" className="text-indigo-600 hover:underline">Portfolio</Link>
                <Link to="/trades" className="text-indigo-600 hover:underline">Trades</Link>
                <Link to="/rules" className="text-indigo-600 hover:underline">Rule configs</Link>
                <Link to="/research/backtests" className="text-indigo-600 hover:underline">Research</Link>
                <Link to="/audit" className="text-indigo-600 hover:underline">Audit log</Link>
                <Link to="/health" className="text-indigo-600 hover:underline">Pipeline health</Link>
              </div>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
