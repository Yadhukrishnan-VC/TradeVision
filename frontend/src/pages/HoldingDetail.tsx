// HoldingDetail — GET /dashboard/portfolio/holdings/:symbol/.
// HoldingSerializer (VERIFIED).

import { useParams, Link } from "react-router-dom";
import { useFetch } from "@/hooks/useFetch";
import { getHolding } from "@/api/dashboard";
import { Card, StatCard, Alert, Breadcrumbs, EmptyState } from "@/components";
import { fmtInr, toNum, pnlColor } from "@/lib/decimal";
import { fmtDate } from "@/lib/time";

export function HoldingDetail() {
  const { symbol } = useParams<{ symbol: string }>();
  const { data, state, error, refetch } = useFetch(() => getHolding(symbol || ""), [symbol]);

  return (
    <div className="space-y-4">
      <Breadcrumbs
        items={[
          { label: "Portfolio", to: "/portfolio" },
          { label: symbol || "—" },
        ]}
      />
      <h1 className="text-2xl font-bold text-slate-900">Holding — {symbol}</h1>

      {state === "loading" && (
        <Card>
          <div className="h-24 bg-slate-100 rounded animate-pulse" />
        </Card>
      )}
      {state === "error" && error && (
        <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>
      )}
      {state === "empty" && (
        <Card><EmptyState title="Holding not found" description={`No holding returned for ${symbol}.`} /></Card>
      )}

      {state === "success" && data && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            <StatCard label="Symbol" value={data.symbol} />
            <StatCard label="Quantity" value={data.quantity} />
            <StatCard label="Avg cost" value={fmtInr(data.avg_cost)} />
            <StatCard label="Cost basis" value={fmtInr(data.cost_basis)} />
            <StatCard label="Market value" value={fmtInr(data.market_value)} />
            <StatCard label="Allocation %" value={toNum(data.allocation_pct) !== null ? `${toNum(data.allocation_pct)!.toFixed(2)}%` : "--"} />
            <StatCard label="Unrealized PnL" value={fmtInr(data.unrealized_pnl)} deltaDirection={toNum(data.unrealized_pnl)! > 0 ? "up" : toNum(data.unrealized_pnl)! < 0 ? "down" : "neutral"} />
            <StatCard label="Opened at" value={fmtDate(data.opened_at)} />
          </div>
          <Card title="Account">
            <code className="text-xs text-slate-700">{data.account_id}</code>
            <div className="text-xs text-slate-500 mt-2">
              <span className={pnlColor(data.unrealized_pnl)}>
                Unrealized PnL: {fmtInr(data.unrealized_pnl)}
              </span>
            </div>
          </Card>
          <div>
            <Link to="/portfolio" className="text-sm text-indigo-600 underline">← Back to portfolio</Link>
          </div>
        </>
      )}
    </div>
  );
}
