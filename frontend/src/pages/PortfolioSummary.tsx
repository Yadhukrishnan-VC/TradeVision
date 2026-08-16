// PortfolioSummary — GET /portfolio/.

import { useFetch } from "@/hooks/useFetch";
import { getPortfolioSummary } from "@/api/secondary";
import { Card, Alert, EmptyState, StatCard } from "@/components";
import { fmtInr, toNum } from "@/lib/decimal";

export function PortfolioSummary() {
  const { data, state, error, refetch } = useFetch(getPortfolioSummary);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Portfolio Summary</h1>
        <p className="text-sm text-slate-500 mt-1">GET /portfolio/ (apps/portfolio)</p>
      </div>
      <Alert tone="warning" title="⚠ Contract not verified">Body shape not verified.</Alert>
      {state === "loading" && <Card><div className="h-24 bg-slate-100 rounded animate-pulse" /></Card>}
      {state === "error" && error && <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>}
      {state === "empty" && <Card><EmptyState title="No portfolio data" /></Card>}
      {state === "success" && data && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard label="Equity" value={fmtInr(data.equity)} />
            <StatCard label="Available capital" value={fmtInr(data.available_capital)} />
            <StatCard label="Cash balance" value={fmtInr(data.cash_balance)} />
            <StatCard label="Market value" value={fmtInr(data.market_value)} />
          </div>
          {data.positions && data.positions.length > 0 && (
            <Card title="Positions">
              <div className="overflow-x-auto tv-scrollbar max-h-96">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-xs text-slate-500">
                      {["Symbol", "Side", "Qty", "Avg cost", "Market value", "Unrealized PnL"].map((h) => (
                        <th key={h} className="px-3 py-2 text-left font-semibold">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.positions.map((p, i) => (
                      <tr key={i} className="border-b border-slate-100">
                        <td className="px-3 py-2 font-medium">{p.symbol}</td>
                        <td className="px-3 py-2">{p.side || "—"}</td>
                        <td className="px-3 py-2 font-mono text-right tabular-nums">{p.quantity || "—"}</td>
                        <td className="px-3 py-2 font-mono text-right tabular-nums">{fmtInr(p.avg_cost)}</td>
                        <td className="px-3 py-2 font-mono text-right tabular-nums">{fmtInr(p.market_value)}</td>
                        <td className={`px-3 py-2 font-mono text-right tabular-nums ${toNum(p.unrealized_pnl)! > 0 ? "text-emerald-600" : toNum(p.unrealized_pnl)! < 0 ? "text-rose-600" : "text-slate-500"}`}>{fmtInr(p.unrealized_pnl)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
