// AnalyticsPnl — GET /dashboard/accounts/:accountId/pnl.
// ⚠ body NOT VERIFIED. Defensive rendering.

import { useParams } from "react-router-dom";
import { useFetch } from "@/hooks/useFetch";
import { getAnalyticsPnl } from "@/api/analytics";
import { Card, Alert, EmptyState, StatCard } from "@/components";
import { fmtInr, toNum, isMissing } from "@/lib/decimal";
import { AnalyticsLayout } from "./_analytics-layout";

export function AnalyticsPnl() {
  const { accountId } = useParams<{ accountId: string }>();
  const { data, state, error, refetch } = useFetch(
    () => getAnalyticsPnl(accountId || ""),
    [accountId]
  );

  return (
    <AnalyticsLayout title="PnL Analytics" description="GET /dashboard/accounts/:accountId/pnl">
      <Alert tone="warning" title="⚠ Contract not verified">
        The exact response body for this endpoint is not verified. Fields are
        rendered defensively; unknown keys ignored, missing keys show "—".
      </Alert>

      {state === "loading" && <Card><div className="h-24 bg-slate-100 rounded animate-pulse" /></Card>}
      {state === "error" && error && (
        <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>
      )}
      {state === "empty" && <Card><EmptyState title="No PnL data" /></Card>}

      {state === "success" && data && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard label="Total realized PnL" value={fmtInr(data.total_realized_pnl)} deltaDirection={sign(data.total_realized_pnl)} />
            <StatCard label="Total unrealized PnL" value={fmtInr(data.total_unrealized_pnl)} deltaDirection={sign(data.total_unrealized_pnl)} />
            <StatCard label="Net PnL" value={fmtInr(data.net_pnl)} deltaDirection={sign(data.net_pnl)} />
          </div>
          {data.by_day && data.by_day.length > 0 && (
            <Card title="Daily PnL" description="by_day[] (defensive)">
              <div className="overflow-x-auto tv-scrollbar max-h-96">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-xs text-slate-500">
                      <th className="px-3 py-2 text-left font-semibold">Date</th>
                      <th className="px-3 py-2 text-right font-semibold">PnL</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_day.map((d, i) => (
                      <tr key={i} className="border-b border-slate-100">
                        <td className="px-3 py-2">{d.date}</td>
                        <td className={`px-3 py-2 font-mono text-right tabular-nums ${sign(d.pnl) === "up" ? "text-emerald-600" : sign(d.pnl) === "down" ? "text-rose-600" : "text-slate-500"}`}>{fmtInr(d.pnl)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
          {data.by_symbol && Object.keys(data.by_symbol).length > 0 && (
            <Card title="By symbol (raw JSON)" description="by_symbol — shape not verified; shown as JSON">
              <pre className="text-[10px] text-slate-700 overflow-x-auto tv-scrollbar">
                {JSON.stringify(data.by_symbol, null, 2)}
              </pre>
            </Card>
          )}
          {/* Render any extra unknown keys as JSON for transparency */}
          <UnknownKeys data={data} knownKeys={["account_id", "total_realized_pnl", "total_unrealized_pnl", "net_pnl", "by_symbol", "by_day"]} />
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

function UnknownKeys<T extends Record<string, unknown>>({ data, knownKeys }: { data: T; knownKeys: string[] }) {
  const extras = Object.keys(data).filter((k) => !knownKeys.includes(k));
  if (extras.length === 0) return null;
  return (
    <Card title="Additional fields" description="rendered defensively as JSON">
      <pre className="text-[10px] text-slate-700 overflow-x-auto tv-scrollbar">
        {JSON.stringify(Object.fromEntries(extras.map((k) => [k, (data as Record<string, unknown>)[k]])), null, 2)}
      </pre>
    </Card>
  );
}
