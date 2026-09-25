// Signals — GET /signals/.

import { useFetch } from "@/hooks/useFetch";
import { getSignals } from "@/api/secondary";
import { Card, Alert, EmptyState, Chip } from "@/components";
import { DataTable, type Column } from "@/components/DataTable";
import { fmtDateTime } from "@/lib/time";
import type { SignalEntry } from "@/types/secondary";

export function Signals() {
  const { data, state, error, refetch } = useFetch(getSignals);

  const dir = (r: SignalEntry) => r.direction || r.side;

  const columns: Column<SignalEntry>[] = [
    { key: "id", header: "ID", cell: (r) => <code className="text-[10px]">{r.id.slice(0, 8)}</code>, sortAccessor: (r) => r.id },
    { key: "instrument_symbol", header: "Symbol", cell: (r) => r.instrument_symbol || r.symbol || "—", sortAccessor: (r) => r.instrument_symbol || r.symbol || "" },
    { key: "timeframe", header: "TF", cell: (r) => r.timeframe ? <Chip tone="slate">{r.timeframe}</Chip> : "—" },
    { key: "direction", header: "Side", cell: (r) => dir(r) ? <Chip tone={dir(r) === "LONG" || dir(r) === "BUY" ? "emerald" : "rose"}>{dir(r)}</Chip> : "—" },
    { key: "confidence_hint", header: "Confidence", numeric: true, cell: (r) => (r.confidence_hint !== undefined && r.confidence_hint !== null) ? String(r.confidence_hint) : "—", sortAccessor: (r) => Number(r.confidence_hint) },
    { key: "source_alert_id", header: "Source alert", cell: (r) => r.source_alert_id ? <code className="text-[10px]">{r.source_alert_id.slice(0, 8)}</code> : "—", sortAccessor: (r) => r.source_alert_id || "" },
    { key: "created_at", header: "Created", cell: (r) => fmtDateTime(r.created_at), sortAccessor: (r) => r.created_at || "" },
  ];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Signals</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">GET /signals/</p>
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
