// PositionDetail — GET /dashboard/positions/live/:id/.

import { useParams, Link } from "react-router-dom";
import { useFetch } from "@/hooks/useFetch";
import { getLivePosition } from "@/api/dashboard";
import { Card, StatCard, Alert, Breadcrumbs, EmptyState, Chip } from "@/components";
import { fmtInr, fmtDecimal, toNum } from "@/lib/decimal";
import { fmtDateTime } from "@/lib/time";

export function PositionDetail() {
  const { id } = useParams<{ id: string }>();
  const { data, state, error, refetch } = useFetch(() => getLivePosition(id || ""), [id]);

  return (
    <div className="space-y-4">
      <Breadcrumbs
        items={[
          { label: "Positions", to: "/positions" },
          { label: id?.slice(0, 8) || "—" },
        ]}
      />
      <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Position detail</h1>

      {state === "loading" && <Card><div className="h-24 bg-slate-100 dark:bg-slate-800 rounded animate-pulse" /></Card>}
      {state === "error" && error && <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>}
      {state === "empty" && <Card><EmptyState title="Position not found" /></Card>}

      {state === "success" && data && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            <StatCard label="Symbol" value={data.symbol} />
            <StatCard label="Side" value={<Chip tone={data.side === "LONG" ? "emerald" : "rose"}>{data.side}</Chip>} />
            <StatCard label="Quantity" value={fmtDecimal(data.quantity || "0", 0)} />
            <StatCard label="Avg cost" value={fmtInr(data.avg_cost)} />
            <StatCard label="Market value" value={fmtInr(data.market_value)} />
            <StatCard label="Unrealized PnL" value={fmtInr(data.unrealized_pnl)} deltaDirection={toNum(data.unrealized_pnl)! > 0 ? "up" : toNum(data.unrealized_pnl)! < 0 ? "down" : "neutral"} />
          </div>
          <Card title="Details">
            <dl className="grid grid-cols-2 md:grid-cols-3 gap-3 text-xs">
              <KV k="Position ID" v={<code className="text-[10px]">{data.position_id}</code>} />
              <KV k="Account ID" v={<code className="text-[10px]">{data.account_id}</code>} />
              <KV k="Opened at" v={fmtDateTime(data.opened_at)} />
            </dl>
          </Card>
          <Link to="/positions" className="text-sm text-indigo-600 underline">← Back to positions</Link>
        </>
      )}
    </div>
  );
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div>
      <dt className="text-slate-500 dark:text-slate-400">{k}</dt>
      <dd className="text-slate-900 dark:text-slate-100 mt-0.5">{v || "—"}</dd>
    </div>
  );
}
