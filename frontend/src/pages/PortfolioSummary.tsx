// PortfolioSummary — GET /portfolio/.

import { useFetch } from "@/hooks/useFetch";
import { getPortfolioPositions, getPortfolioSummary } from "@/api/secondary";
import { Card, Alert, EmptyState, StatCard } from "@/components";
import { fmtInr, toNum } from "@/lib/decimal";

export function PortfolioSummary() {
  const summary = useFetch(getPortfolioSummary);
  const positions = useFetch(getPortfolioPositions);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Portfolio Summary</h1>
        <p className="text-sm text-slate-500 mt-1">GET /portfolio/ + /portfolio/positions/ (apps/portfolio)</p>
      </div>
      {summary.state === "loading" && <Card><div className="h-24 bg-slate-100 rounded animate-pulse" /></Card>}
      {summary.state === "error" && summary.error && <Alert tone="error" code={summary.error.code} onRetry={summary.refetch}>{summary.error.message}</Alert>}
      {summary.state === "empty" && <Card><EmptyState title="No portfolio data" /></Card>}
      {summary.state === "success" && summary.data && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard label="Equity" value={fmtInr(summary.data.equity)} />
            <StatCard label="Available capital" value={fmtInr(summary.data.available_capital)} />
            <StatCard label="Cash" value={fmtInr(summary.data.cash)} />
            <StatCard label="Margin used" value={fmtInr(summary.data.margin_used)} />
            <StatCard label="Realized PnL today" value={fmtInr(summary.data.realized_pnl_today)} />
            <StatCard label="Unrealized PnL today" value={fmtInr(summary.data.unrealized_pnl_today)} />
          </div>
        </div>
      )}
      <Card title="Open positions">
        {positions.state === "error" && positions.error && <Alert tone="error" code={positions.error.code} onRetry={positions.refetch}>{positions.error.message}</Alert>}
        {positions.state === "empty" && <EmptyState title="No open positions" />}
        {positions.state === "success" && positions.data && positions.data.length > 0 && (
          <div className="overflow-x-auto tv-scrollbar max-h-96">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-xs text-slate-500">
                  {["Symbol", "Side", "Qty", "Avg entry", "Current", "Unrealized PnL", "Exposure"].map((h) => (
                    <th key={h} className="px-3 py-2 text-left font-semibold">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {positions.data.map((p, i) => (
                  <tr key={i} className="border-b border-slate-100">
                    <td className="px-3 py-2 font-medium">{p.symbol}</td>
                    <td className="px-3 py-2">{p.side || "—"}</td>
                    <td className="px-3 py-2 font-mono text-right tabular-nums">{p.quantity || "—"}</td>
                    <td className="px-3 py-2 font-mono text-right tabular-nums">{fmtInr(p.avg_entry_price)}</td>
                    <td className="px-3 py-2 font-mono text-right tabular-nums">{p.current_price != null ? fmtInr(p.current_price) : "—"}</td>
                    <td className={`px-3 py-2 font-mono text-right tabular-nums ${toNum(p.unrealized_pnl)! > 0 ? "text-emerald-600" : toNum(p.unrealized_pnl)! < 0 ? "text-rose-600" : "text-slate-500"}`}>{fmtInr(p.unrealized_pnl)}</td>
                    <td className="px-3 py-2 font-mono text-right tabular-nums">{fmtInr(p.exposure)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}