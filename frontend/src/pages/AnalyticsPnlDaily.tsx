// AnalyticsPnlDaily — GET /dashboard/accounts/:accountId/pnl/daily.

import { useParams } from "react-router-dom";
import { useFetch } from "@/hooks/useFetch";
import { getAnalyticsPnlDaily } from "@/api/analytics";
import { Card, Alert, EmptyState } from "@/components";
import { EquityCurve } from "@/components/charts";
import { AnalyticsLayout } from "./_analytics-layout";
import { toNum } from "@/lib/decimal";

export function AnalyticsPnlDaily() {
  const { accountId } = useParams<{ accountId: string }>();
  const { data, state, error, refetch } = useFetch(
    () => getAnalyticsPnlDaily(accountId || ""),
    [accountId]
  );

  // Build a cumulative series from daily[] if present.
  const series = (data?.daily || []).map((d) => {
    const v = toNum(d.pnl);
    return { label: d.date, value: v };
  });
  // Cumulative
  let cum = 0;
  const cumulative = series.map((p) => {
    if (p.value !== null) cum += p.value;
    return { label: p.label, value: cum };
  });

  return (
    <AnalyticsLayout title="Daily Rollup" description="GET /dashboard/accounts/:accountId/pnl/daily">
      <Alert tone="warning" title="⚠ Contract not verified">
        Body is not verified. If <code>daily[]</code> of <code>{"{date, pnl}"}</code> is present, an equity-curve chart is plotted.
      </Alert>
      {state === "loading" && <Card><div className="h-24 bg-slate-100 rounded animate-pulse" /></Card>}
      {state === "error" && error && <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>}
      {state === "empty" && <Card><EmptyState title="No daily data" /></Card>}
      {state === "success" && data && (
        <div className="space-y-4">
          {cumulative.length > 0 ? (
            <Card title="Cumulative PnL" description="derived from daily[].pnl">
              <EquityCurve series={cumulative} height={240} />
            </Card>
          ) : (
            <Card title="Cumulative PnL">
              <EmptyState title="No daily series" description="The response did not include a daily[] series." />
            </Card>
          )}
          {cumulative.length > 0 && (
            <Card title="Daily PnL table">
              <div className="overflow-x-auto tv-scrollbar max-h-96">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-xs text-slate-500">
                      <th className="px-3 py-2 text-left font-semibold">Date</th>
                      <th className="px-3 py-2 text-right font-semibold">Daily PnL</th>
                      <th className="px-3 py-2 text-right font-semibold">Cumulative</th>
                    </tr>
                  </thead>
                  <tbody>
                    {series.map((p, i) => (
                      <tr key={i} className="border-b border-slate-100">
                        <td className="px-3 py-2">{p.label}</td>
                        <td className={`px-3 py-2 font-mono text-right tabular-nums ${p.value! > 0 ? "text-emerald-600" : p.value! < 0 ? "text-rose-600" : "text-slate-500"}`}>₹{p.value?.toLocaleString("en-IN", { maximumFractionDigits: 2 }) ?? "--"}</td>
                        <td className={`px-3 py-2 font-mono text-right tabular-nums ${cumulative[i].value! > 0 ? "text-emerald-600" : cumulative[i].value! < 0 ? "text-rose-600" : "text-slate-500"}`}>₹{cumulative[i].value?.toLocaleString("en-IN", { maximumFractionDigits: 2 }) ?? "--"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </div>
      )}
    </AnalyticsLayout>
  );
}
