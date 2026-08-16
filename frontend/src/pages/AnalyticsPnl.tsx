// AnalyticsPnl — GET /dashboard/accounts/:accountId/pnl.
// Verified against backend.

import { useParams } from "react-router-dom";
import { useFetch } from "@/hooks/useFetch";
import { getAnalyticsPnl } from "@/api/analytics";
import { Card, Alert, EmptyState, StatCard } from "@/components";
import { fmtInr, fmtPct, toNum, isMissing } from "@/lib/decimal";
import { AnalyticsLayout } from "./_analytics-layout";

export function AnalyticsPnl() {
  const { accountId } = useParams<{ accountId: string }>();
  const { data, state, error, refetch } = useFetch(
    () => getAnalyticsPnl(accountId || ""),
    [accountId]
  );

  return (
    <AnalyticsLayout title="PnL Analytics" description="GET /dashboard/accounts/:accountId/pnl">
      {state === "loading" && <Card><div className="h-24 bg-slate-100 rounded animate-pulse" /></Card>}
      {state === "error" && error && (
        <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>
      )}
      {state === "empty" && <Card><EmptyState title="No PnL data" /></Card>}

      {state === "success" && data && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard label="Current total PnL" value={fmtInr(data.current_total_pnl)} deltaDirection={sign(data.current_total_pnl)} />
            <StatCard label="Current unrealized PnL" value={fmtInr(data.current_unrealized_pnl)} deltaDirection={sign(data.current_unrealized_pnl)} />
            <StatCard label="Peak cumulative PnL" value={fmtInr(data.peak_cumulative_pnl)} />
            <StatCard label="Current drawdown" value={fmtPct(data.current_drawdown_pct)} />
          </div>
          {Array.isArray(data.time_series) && data.time_series.length > 0 && (
            <Card title="Time series" description={`${data.time_series.length} points (${data.metadata?.period ?? "unknown"} period)`}>
              <div className="overflow-x-auto tv-scrollbar max-h-96">
                <pre className="text-[10px] text-slate-700 overflow-x-auto tv-scrollbar">
                  {JSON.stringify(data.time_series, null, 2)}
                </pre>
              </div>
            </Card>
          )}
        </div>
      )}
    </AnalyticsLayout>
  );
}

function sign(v: unknown): "up" | "down" | "neutral" {
  if (isMissing(v)) return "neutral";
  const n = toNum(v as string);
  if (n === null) return "neutral";
  return n > 0 ? "up" : n < 0 ? "down" : "neutral";
}
