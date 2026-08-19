// AnalyticsPerformance — GET /dashboard/accounts/:accountId/performance.
// Verified against backend.

import { useParams } from "react-router-dom";
import { useFetch } from "@/hooks/useFetch";
import { getAnalyticsPerformance } from "@/api/analytics";
import { Card, Alert, EmptyState, StatCard } from "@/components";
import { AnalyticsLayout } from "./_analytics-layout";
import { fmtPct, fmtRatio, fmtInr, isMissing } from "@/lib/decimal";

export function AnalyticsPerformance() {
  const { accountId } = useParams<{ accountId: string }>();
  const { data, state, error, refetch } = useFetch(
    () => getAnalyticsPerformance(accountId || ""),
    [accountId]
  );

  return (
    <AnalyticsLayout title="Performance" description="GET /dashboard/accounts/:accountId/performance">
      {state === "loading" && <Card><div className="h-24 bg-slate-100 dark:bg-slate-800 rounded animate-pulse" /></Card>}
      {state === "error" && error && <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>}
      {state === "empty" && <Card><EmptyState title="No performance data" /></Card>}
      {state === "success" && data && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          <StatCard label="Win rate" value={fmtPct(data.win_rate)} />
          <StatCard label="Avg win" value={fmtInr(data.avg_win)} />
          <StatCard label="Avg loss" value={fmtInr(data.avg_loss)} />
          <StatCard label="Expectancy" value={isMissing(data.expectancy) ? "—" : fmtInr(data.expectancy)} />
          <StatCard label="Profit factor" value={fmtRatio(data.profit_factor)} />
          <StatCard label="Sharpe-like ratio" value={fmtRatio(data.sharpe_like_ratio)} />
          <StatCard label="Total trades" value={data.total_trades?.toString() ?? "—"} />
          <StatCard label="Winning" value={data.winning_trades?.toString() ?? "—"} />
          <StatCard label="Losing" value={data.losing_trades?.toString() ?? "—"} />
        </div>
      )}
    </AnalyticsLayout>
  );
}
