// AnalyticsPerformance — GET /dashboard/accounts/:accountId/performance.

import { useParams } from "react-router-dom";
import { useFetch } from "@/hooks/useFetch";
import { getAnalyticsPerformance } from "@/api/analytics";
import { Card, Alert, EmptyState, StatCard } from "@/components";
import { AnalyticsLayout } from "./_analytics-layout";
import { fmtPct, fmtRatio, isMissing } from "@/lib/decimal";

export function AnalyticsPerformance() {
  const { accountId } = useParams<{ accountId: string }>();
  const { data, state, error, refetch } = useFetch(
    () => getAnalyticsPerformance(accountId || ""),
    [accountId]
  );

  return (
    <AnalyticsLayout title="Performance" description="GET /dashboard/accounts/:accountId/performance">
      <Alert tone="warning" title="⚠ Contract not verified">
        Body is not verified; defensive rendering.
      </Alert>
      {state === "loading" && <Card><div className="h-24 bg-slate-100 rounded animate-pulse" /></Card>}
      {state === "error" && error && <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>}
      {state === "empty" && <Card><EmptyState title="No performance data" /></Card>}
      {state === "success" && data && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          <StatCard label="Sharpe ratio" value={fmtRatio(data.sharpe_ratio)} />
          <StatCard label="Sortino ratio" value={fmtRatio(data.sortino_ratio)} />
          <StatCard label="Max drawdown %" value={fmtPct(data.max_drawdown_pct)} />
          <StatCard label="Win rate" value={fmtPct(data.win_rate)} />
          <StatCard label="Expectancy" value={isMissing(data.expectancy) ? "—" : `₹${data.expectancy}`} />
          <StatCard label="Profit factor" value={fmtRatio(data.profit_factor)} />
          <StatCard label="Benchmark return %" value={fmtPct(data.benchmark_return_pct)} />
        </div>
      )}
    </AnalyticsLayout>
  );
}
