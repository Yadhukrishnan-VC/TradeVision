// Portfolio composition — GET /dashboard/portfolio/composition/.
// Verified fields: account_id, total_market_value, total_cost_basis, cash_balance, holdings[].

import { useFetch } from "@/hooks/useFetch";
import { getPortfolioComposition } from "@/api/dashboard";
import { Card, StatCard, Alert, EmptyState } from "@/components";
import { Donut } from "@/components/charts";
import { fmtInr, toNum } from "@/lib/decimal";
import { Link } from "react-router-dom";
import type { Holding } from "@/types/dashboard";

export function Portfolio() {
  const { data, state, error, refetch } = useFetch(getPortfolioComposition);

  if (state === "loading") return <LoadingPortfolio />;
  if (state === "error" && error) {
    return (
      <Alert tone="error" code={error.code} onRetry={refetch}>
        {error.message}
      </Alert>
    );
  }
  if (state === "empty" || !data) {
    return (
      <Card>
        <EmptyState title="No portfolio data" description="No composition returned by the API." />
      </Card>
    );
  }

  const holdings = data.holdings || [];
  const donutData = holdings
    .map((h) => ({
      label: h.symbol,
      value: toNum(h.allocation_pct) ?? 0,
    }))
    .filter((d) => d.value > 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Portfolio Composition</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Account <code className="text-xs">{data.account_id?.slice(0, 8) || "—"}</code></p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <StatCard label="Total market value" value={fmtInr(data.total_market_value)} />
        <StatCard label="Total cost basis" value={fmtInr(data.total_cost_basis)} />
        <StatCard label="Cash balance" value={fmtInr(data.cash_balance)} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="Allocation" description="holdings[].allocation_pct">
          {donutData.length === 0 ? (
            <EmptyState title="No allocations" description="No holdings with positive allocation." />
          ) : (
            <Donut
              data={donutData}
              height={280}
              centerLabel="Holdings"
              centerValue={`${donutData.length}`}
            />
          )}
        </Card>
        <Card title="Holdings" description={`${holdings.length} holding(s)`}>
          {holdings.length === 0 ? (
            <EmptyState title="No holdings" />
          ) : (
            <div className="overflow-x-auto tv-scrollbar max-h-96">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 dark:border-slate-800 text-xs text-slate-500 dark:text-slate-400">
                    {["Symbol", "Qty", "Avg cost", "Market value", "Alloc %", "Unrealized PnL"].map((h) => (
                      <th key={h} className="px-3 py-2 text-left font-semibold">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {holdings.map((h: Holding) => (
                    <tr key={h.symbol} className="border-b border-slate-100 dark:border-slate-800 hover:bg-slate-50">
                      <td className="px-3 py-2"><Link to={`/portfolio/holdings/${encodeURIComponent(h.symbol)}`} className="text-indigo-600 hover:underline">{h.symbol}</Link></td>
                      <td className="px-3 py-2 font-mono text-right tabular-nums">{h.quantity}</td>
                      <td className="px-3 py-2 font-mono text-right tabular-nums">{fmtInr(h.avg_cost)}</td>
                      <td className="px-3 py-2 font-mono text-right tabular-nums">{fmtInr(h.market_value)}</td>
                      <td className="px-3 py-2 font-mono text-right tabular-nums">{toNum(h.allocation_pct) !== null ? `${toNum(h.allocation_pct)!.toFixed(2)}%` : "--"}</td>
                      <td className={`px-3 py-2 font-mono text-right tabular-nums ${toNum(h.unrealized_pnl)! > 0 ? "text-emerald-600" : toNum(h.unrealized_pnl)! < 0 ? "text-rose-600" : "text-slate-500 dark:text-slate-400"}`}>{fmtInr(h.unrealized_pnl)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

function LoadingPortfolio() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Portfolio Composition</h1>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm rounded-lg p-4">
            <div className="h-3 w-20 bg-slate-200 dark:bg-slate-700 rounded animate-pulse mb-2" />
            <div className="h-6 w-28 bg-slate-200 dark:bg-slate-700 rounded animate-pulse mb-2" />
            <div className="h-2.5 w-16 bg-slate-100 dark:bg-slate-800 rounded animate-pulse" />
          </div>
        ))}
      </div>
    </div>
  );
}
