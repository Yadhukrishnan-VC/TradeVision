// AnalyticsRisk — GET /dashboard/accounts/:accountId/risk.

import { useParams } from "react-router-dom";
import { useFetch } from "@/hooks/useFetch";
import { getAnalyticsRisk } from "@/api/analytics";
import { Card, Alert, EmptyState, StatCard } from "@/components";
import { AnalyticsLayout } from "./_analytics-layout";
import { fmtInr, isMissing } from "@/lib/decimal";

export function AnalyticsRisk() {
  const { accountId } = useParams<{ accountId: string }>();
  const { data, state, error, refetch } = useFetch(
    () => getAnalyticsRisk(accountId || ""),
    [accountId]
  );

  return (
    <AnalyticsLayout title="Risk Summary" description="GET /dashboard/accounts/:accountId/risk">
      <Alert tone="warning" title="⚠ Contract not verified">
        Body is not verified; defensive rendering.
      </Alert>
      {state === "loading" && <Card><div className="h-24 bg-slate-100 rounded animate-pulse" /></Card>}
      {state === "error" && error && <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>}
      {state === "empty" && <Card><EmptyState title="No risk summary" /></Card>}
      {state === "success" && data && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          <StatCard label="VaR 95" value={isMissing(data.var_95) ? "—" : fmtInr(data.var_95)} />
          <StatCard label="VaR 99" value={isMissing(data.var_99) ? "—" : fmtInr(data.var_99)} />
          <StatCard label="Exposure" value={isMissing(data.exposure) ? "—" : fmtInr(data.exposure)} />
          <StatCard label="Leverage" value={isMissing(data.leverage) ? "—" : data.leverage} />
        </div>
      )}
    </AnalyticsLayout>
  );
}
