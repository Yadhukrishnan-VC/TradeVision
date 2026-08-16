// TraderMemory — GET /trader-memory/entries/ + /projections/:strategyId/.

import { useState } from "react";
import { useFetch } from "@/hooks/useFetch";
import { getTraderMemoryEntries, getTraderMemoryProjection } from "@/api/secondary";
import { Card, Alert, EmptyState, Button } from "@/components";
import { DataTable, type Column } from "@/components/DataTable";
import { fmtDateTime } from "@/lib/time";
import type { TraderMemoryEntry } from "@/types/secondary";

export function TraderMemory() {
  const { data, state, error, refetch } = useFetch(getTraderMemoryEntries);
  const [strategyId, setStrategyId] = useState("");
  const [fetchStrategy, setFetchStrategy] = useState<string | null>(null);
  const projection = useFetch(
    () => (fetchStrategy ? getTraderMemoryProjection(fetchStrategy) : Promise.resolve(null as never)),
    [fetchStrategy]
  );

  const columns: Column<TraderMemoryEntry>[] = [
    { key: "id", header: "ID", cell: (r) => <code className="text-[10px]">{r.id.slice(0, 8)}</code>, sortAccessor: (r) => r.id },
    { key: "strategy_id", header: "Strategy", cell: (r) => r.strategy_id ? <code className="text-xs">{r.strategy_id}</code> : "—", sortAccessor: (r) => r.strategy_id || "" },
    { key: "symbol", header: "Symbol", cell: (r) => r.symbol || "—", sortAccessor: (r) => r.symbol || "" },
    { key: "notes", header: "Notes", cell: (r) => <span className="text-xs text-slate-600 truncate inline-block max-w-md">{r.notes || "—"}</span> },
    { key: "created_at", header: "Created", cell: (r) => fmtDateTime(r.created_at), sortAccessor: (r) => r.created_at || "" },
  ];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Trader Memory</h1>
        <p className="text-sm text-slate-500 mt-1">GET /trader-memory/entries/ + /projections/:strategyId/</p>
      </div>
      <Alert tone="warning" title="⚠ Contract not verified">Body shape not verified.</Alert>
      {state === "error" && error && <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>}

      <Card title="Strategy projection" description="GET /trader-memory/projections/:strategyId/">
        <form
          onSubmit={(e) => { e.preventDefault(); setFetchStrategy(strategyId); }}
          className="flex items-end gap-2 mb-3"
        >
          <label className="block flex-1">
            <span className="block text-xs font-medium text-slate-700 mb-1">Strategy ID</span>
            <input className="tv-input" value={strategyId} onChange={(e) => setStrategyId(e.target.value)} placeholder="e.g. breakout_v1" required />
          </label>
          <Button type="submit" variant="primary">Fetch projection</Button>
        </form>
        {fetchStrategy && projection.state === "loading" && (
          <div className="text-sm text-slate-500 italic">Loading projection for {fetchStrategy}…</div>
        )}
        {projection.state === "error" && projection.error && (
          <Alert tone="error" code={projection.error.code} onRetry={projection.refetch}>{projection.error.message}</Alert>
        )}
        {projection.state === "success" && projection.data && (
          <div className="bg-slate-50 p-3 rounded-md">
            <div className="text-xs text-slate-500 mb-1">Strategy: <code className="text-[10px]">{projection.data.strategy_id}</code></div>
            <pre className="text-xs text-slate-700 overflow-x-auto tv-scrollbar">
              {JSON.stringify(projection.data.metrics || {}, null, 2)}
            </pre>
          </div>
        )}
      </Card>

      <Card title="Memory entries">
        {state === "loading" ? (
          <DataTable columns={columns} rows={[]} loading rowKey={(_, i) => String(i)} />
        ) : !data || data.results.length === 0 ? (
          <EmptyState title="No memory entries" />
        ) : (
          <DataTable columns={columns} rows={data.results} rowKey={(r) => r.id} initialSortKey="created_at" initialSortDir="desc" />
        )}
      </Card>
    </div>
  );
}
