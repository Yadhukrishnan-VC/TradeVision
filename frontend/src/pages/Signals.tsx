// Signals — GET /signals/.

import { useFetch } from "@/hooks/useFetch";
import { getSignals } from "@/api/secondary";
import { Card, Alert, EmptyState, Chip } from "@/components";
import { DataTable, type Column } from "@/components/DataTable";
import { fmtDateTime } from "@/lib/time";
import type { SignalEntry } from "@/types/secondary";

export function Signals() {
  const { data, state, error, refetch } = useFetch(getSignals);

  const columns: Column<SignalEntry>[] = [
    { key: "id", header: "ID", cell: (r) => <code className="text-[10px]">{r.id.slice(0, 8)}</code>, sortAccessor: (r) => r.id },
    { key: "symbol", header: "Symbol", cell: (r) => r.symbol || "—", sortAccessor: (r) => r.symbol || "" },
    { key: "rule_id", header: "Rule", cell: (r) => r.rule_id ? <Chip tone="violet">{r.rule_id}</Chip> : "—", sortAccessor: (r) => r.rule_id || "" },
    { key: "side", header: "Side", cell: (r) => r.side ? <Chip tone={r.side === "LONG" || r.side === "BUY" ? "emerald" : "rose"}>{r.side}</Chip> : "—" },
    { key: "status", header: "Status", cell: (r) => r.status ? <Chip tone="amber">{r.status}</Chip> : "—" },
    { key: "created_at", header: "Created", cell: (r) => fmtDateTime(r.created_at), sortAccessor: (r) => r.created_at || "" },
  ];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Signals</h1>
        <p className="text-sm text-slate-500 mt-1">GET /signals/</p>
      </div>
      <Alert tone="warning" title="⚠ Contract not verified">Body shape not verified.</Alert>
      {state === "error" && error && <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>}
      <Card>
        {state === "loading" ? (
          <DataTable columns={columns} rows={[]} loading rowKey={(_, i) => String(i)} />
        ) : !data || data.results.length === 0 ? (
          <EmptyState title="No signals" />
        ) : (
          <DataTable columns={columns} rows={data.results} rowKey={(r) => r.id} initialSortKey="created_at" initialSortDir="desc" />
        )}
      </Card>
    </div>
  );
}
