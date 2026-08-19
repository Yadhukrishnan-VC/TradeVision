// OrderDetail — GET /dashboard/orders/:id/.

import { useParams, Link } from "react-router-dom";
import { useFetch } from "@/hooks/useFetch";
import { getOrder } from "@/api/dashboard";
import { Card, StatCard, Alert, Breadcrumbs, EmptyState, Chip } from "@/components";
import { fmtInr, fmtDecimal } from "@/lib/decimal";
import { fmtDateTime } from "@/lib/time";

export function OrderDetail() {
  const { id } = useParams<{ id: string }>();
  const { data, state, error, refetch } = useFetch(() => getOrder(id || ""), [id]);

  return (
    <div className="space-y-4">
      <Breadcrumbs
        items={[
          { label: "Orders", to: "/orders" },
          { label: id?.slice(0, 8) || "—" },
        ]}
      />
      <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Order detail</h1>

      {state === "loading" && <Card><div className="h-24 bg-slate-100 dark:bg-slate-800 rounded animate-pulse" /></Card>}
      {state === "error" && error && <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>}
      {state === "empty" && <Card><EmptyState title="Order not found" /></Card>}

      {state === "success" && data && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            <StatCard label="Symbol" value={data.symbol} />
            <StatCard label="Side" value={<Chip tone={data.side === "LONG" ? "emerald" : "rose"}>{data.side}</Chip>} />
            <StatCard label="Quantity" value={fmtDecimal(data.quantity || "0", 0)} />
            <StatCard label="Entry price" value={fmtInr(data.entry_price)} />
            <StatCard label="Avg fill price" value={fmtInr(data.avg_fill_price)} />
            <StatCard label="Filled quantity" value={fmtDecimal(data.filled_quantity || "0", 0)} />
            <StatCard label="Status" value={<Chip tone={data.status === "FILLED" ? "emerald" : data.status === "REJECTED" ? "rose" : "amber"}>{data.status}</Chip>} />
            <StatCard label="Created" value={fmtDateTime(data.created_at)} />
          </div>
          <Card title="Details">
            <dl className="grid grid-cols-2 md:grid-cols-3 gap-3 text-xs">
              <KV k="Order ID" v={<code className="text-[10px]">{data.order_id}</code>} />
              <KV k="Account ID" v={<code className="text-[10px]">{data.account_id}</code>} />
              <KV k="Correlation ID" v={<code className="text-[10px]">{data.correlation_id || "—"}</code>} />
            </dl>
          </Card>
          <Link to="/orders" className="text-sm text-indigo-600 underline">← Back to orders</Link>
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
