// RawIngestionEvents — GET /ingestion/raw-events/.
// Per decision #12: included as a read-only secondary System page.

import { useFetch } from "@/hooks/useFetch";
import { getIngestionRawEvents } from "@/api/secondary";
import { Card, Alert, EmptyState, Chip } from "@/components";
import { DataTable, type Column } from "@/components/DataTable";
import { fmtDateTime } from "@/lib/time";
import type { IngestionRawEvent } from "@/types/secondary";

export function RawIngestionEvents() {
  const { data, state, error, refetch } = useFetch(getIngestionRawEvents);

  const columns: Column<IngestionRawEvent>[] = [
    { key: "id", header: "ID", cell: (r) => <code className="text-[10px]">{r.id.slice(0, 8)}</code>, sortAccessor: (r) => r.id },
    { key: "provider", header: "Provider", cell: (r) => r.provider ? <Chip tone="blue">{r.provider}</Chip> : "—", sortAccessor: (r) => r.provider || "" },
    { key: "symbol", header: "Symbol", cell: (r) => r.symbol || "—", sortAccessor: (r) => r.symbol || "" },
    { key: "received_at", header: "Received", cell: (r) => fmtDateTime(r.received_at), sortAccessor: (r) => r.received_at || "" },
    {
      key: "raw_payload",
      header: "Payload",
      cell: (r) => (
        <details>
          <summary className="text-xs text-indigo-600 cursor-pointer">view</summary>
          <pre className="text-[10px] text-slate-700 dark:text-slate-300 mt-1 max-h-40 overflow-y-auto tv-scrollbar">
            {JSON.stringify(r.raw_payload, null, 2)}
          </pre>
        </details>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Raw Ingestion Events</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          GET /ingestion/raw-events/ ·{" "}
          <span className="text-amber-700">secondary, read-only operational view</span>
        </p>
      </div>
      <Alert tone="warning" title="⚠ Contract not verified">
        Body shape not verified. This is a secondary operational/debugging page.
      </Alert>
      {state === "error" && error && <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>}
      <Card>
        {state === "loading" ? (
          <DataTable columns={columns} rows={[]} loading rowKey={(_, i) => String(i)} />
        ) : !data || data.results.length === 0 ? (
          <EmptyState title="No raw events" />
        ) : (
          <DataTable columns={columns} rows={data.results} rowKey={(r) => r.id} initialSortKey="received_at" initialSortDir="desc" />
        )}
      </Card>
    </div>
  );
}
