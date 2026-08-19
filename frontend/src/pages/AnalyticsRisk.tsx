// AnalyticsRisk — GET /dashboard/accounts/:accountId/risk.
// Verified against backend.

import { useParams } from "react-router-dom";
import { useFetch } from "@/hooks/useFetch";
import { getAnalyticsRisk } from "@/api/analytics";
import { Card, Alert, EmptyState, StatCard } from "@/components";
import { AnalyticsLayout } from "./_analytics-layout";
import { fmtInr, fmtPct, isMissing } from "@/lib/decimal";

export function AnalyticsRisk() {
  const { accountId } = useParams<{ accountId: string }>();
  const { data, state, error, refetch } = useFetch(
    () => getAnalyticsRisk(accountId || ""),
    [accountId]
  );

  return (
    <AnalyticsLayout title="Risk Summary" description="GET /dashboard/accounts/:accountId/risk">
      {state === "loading" && <Card><div className="h-24 bg-slate-100 dark:bg-slate-800 rounded animate-pulse" /></Card>}
      {state === "error" && error && <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>}
      {state === "empty" && <Card><EmptyState title="No risk summary" /></Card>}
      {state === "success" && data && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          <StatCard label="Total exposure" value={isMissing(data.total_exposure) ? "—" : fmtInr(data.total_exposure)} />
          <StatCard label="Largest position" value={isMissing(data.largest_position_pct) ? "—" : fmtPct(data.largest_position_pct)} />
          <StatCard label="Sector concentration" value={isMissing(data.sector_concentration_pct) ? "—" : fmtPct(data.sector_concentration_pct)} />
          <StatCard label="Leverage ratio" value={isMissing(data.leverage_ratio) ? "—" : data.leverage_ratio} />
        </div>
      )}
      {state === "success" && data && Array.isArray(data.active_alerts) && data.active_alerts.length > 0 && (
        <Card title="Active alerts">
          <pre className="text-[10px] text-slate-700 dark:text-slate-300 overflow-x-auto tv-scrollbar">
            {JSON.stringify(data.active_alerts, null, 2)}
          </pre>
        </Card>
      )}
    </AnalyticsLayout>
  );
}
