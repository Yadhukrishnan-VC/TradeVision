// AnalyticsPnlDaily — GET /dashboard/accounts/:accountId/pnl/daily.
// Verified against backend: returns an array of {trading_date, realized_pnl, total_pnl, cumulative_pnl}.

import { useParams } from "react-router-dom";
import { useFetch } from "@/hooks/useFetch";
import { getAnalyticsPnlDaily } from "@/api/analytics";
import { Card, Alert, EmptyState } from "@/components";
import { EquityCurve } from "@/components/charts";
import { AnalyticsLayout } from "./_analytics-layout";
import { toNum } from "@/lib/decimal";

const fmt = (v: number | null) =>
  v === null || v === undefined ? "--" : `₹${v.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

export function AnalyticsPnlDaily() {
  const { accountId } = useParams<{ accountId: string }>();
  const { data, state, error, refetch } = useFetch(
    () => getAnalyticsPnlDaily(accountId || "", "2000-01-01", "2099-12-31"),
    [accountId]
  );

  // Build a cumulative series from the rollup array.
  const series = (data || []).map((d) => {
    const v = toNum(d.total_pnl);
    return { label: d.trading_date, value: v };
  });
  // Cumulative
  let cum = 0;
  const cumulative = series.map((p) => {
    if (p.value !== null) cum += p.value;
    return { label: p.label, value: cum };
  });

  return (
    <AnalyticsLayout title="Daily Rollup" description="GET /dashboard/accounts/:accountId/pnl/daily">
      {state === "loading" && <Card><div className="h-24 bg-slate-100 rounded animate-pulse" /></Card>}
      {state === "error" && error && <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>}
      {state === "empty" && <Card><EmptyState title="No daily data" /></Card>}
      {state === "success" && data && (
        <div className="space-y-4">
          {cumulative.length > 0 ? (
            <Card title="Cumulative PnL" description="derived from rollup[].total_pnl">
              <EquityCurve series={cumulative} height={240} />
            </Card>
          ) : (
            <Card title="Cumulative PnL">
              <EmptyState title="No daily series" description="The response did not include any rollup rows." />
            </Card>
          )}
          {cumulative.length > 0 && (
            <Card title="Daily PnL table">
              <div className="overflow-x-auto tv-scrollbar max-h-96">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-xs text-slate-500">
                      <th className="px-3 py-2 text-left font-semibold">Date</th>
                      <th className="px-3 py-2 text-right font-semibold">Realized</th>
                      <th className="px-3 py-2 text-right font-semibold">Total PnL</th>
                      <th className="px-3 py-2 text-right font-semibold">Cumulative</th>
                    </tr>
                  </thead>
                  <tbody>
                    {series.map((p, i) => (
                      <tr key={i} className="border-b border-slate-100">
                        <td className="px-3 py-2">{p.label}</td>
                        <td className={`px-3 py-2 font-mono text-right tabular-nums ${(data[i].realized_pnl ? toNum(data[i].realized_pnl) : 0)! > 0 ? "text-emerald-600" : (data[i].realized_pnl ? toNum(data[i].realized_pnl) : 0)! < 0 ? "text-rose-600" : "text-slate-500"}`}>{fmt(toNum(data[i].realized_pnl))}</td>
                        <td className={`px-3 py-2 font-mono text-right tabular-nums ${p.value! > 0 ? "text-emerald-600" : p.value! < 0 ? "text-rose-600" : "text-slate-500"}`}>{fmt(p.value)}</td>
                        <td className={`px-3 py-2 font-mono text-right tabular-nums ${cumulative[i].value! > 0 ? "text-emerald-600" : cumulative[i].value! < 0 ? "text-rose-600" : "text-slate-500"}`}>{fmt(cumulative[i].value)}</td>
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
