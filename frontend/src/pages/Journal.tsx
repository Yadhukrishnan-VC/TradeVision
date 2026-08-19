// Journal — GET /journal/entries/ (+ detail by correlationId).
// Body VERIFIED 2026-08-17: bare array list, requires `account_id` query param.

import { useParams, Link, useSearchParams } from "react-router-dom";
import { useFetch } from "@/hooks/useFetch";
import { getJournalEntries, getJournalEntry } from "@/api/system";
import { Card, Alert, EmptyState, Chip, Breadcrumbs } from "@/components";
import { DataTable, type Column } from "@/components/DataTable";
import { fmtDateTime } from "@/lib/time";
import type { JournalEntry } from "@/types/secondary";

export function Journal() {
  const { correlationId } = useParams<{ correlationId: string }>();

  if (correlationId) return <JournalDetail correlationId={correlationId} />;
  return <JournalList />;
}

const outcomeTone: Record<string, "emerald" | "rose" | "slate" | "amber"> = {
  won: "emerald",
  lost: "rose",
  breakeven: "amber",
};

function JournalList() {
  const [params] = useSearchParams();
  const accountId = params.get("account_id") || undefined;
  const { data, state, error, refetch } = useFetch(
    () => getJournalEntries(accountId),
    [accountId]
  );
  const rows: JournalEntry[] = data || [];

  const columns: Column<JournalEntry>[] = [
    {
      key: "correlation_id",
      header: "Correlation ID",
      cell: (r) => (
        <Link to={`/journal/${r.correlation_id}`} className="text-indigo-600 hover:underline">
          <code className="text-[10px]">{r.correlation_id.slice(0, 8)}</code>
        </Link>
      ),
      sortAccessor: (r) => r.correlation_id,
    },
    {
      key: "symbol",
      header: "Symbol",
      cell: (r) => <span className="font-medium">{r.signal_snapshot?.symbol || "—"}</span>,
      sortAccessor: (r) => r.signal_snapshot?.symbol || "",
    },
    {
      key: "decision",
      header: "Decision",
      cell: (r) => r.decision_snapshot?.decision || "—",
      sortAccessor: (r) => r.decision_snapshot?.decision || "",
    },
    {
      key: "outcome",
      header: "Outcome",
      cell: (r) =>
        r.outcome ? (
          <Chip tone={outcomeTone[r.outcome] || "slate"}>{r.outcome}</Chip>
        ) : (
          <span className="text-slate-400 dark:text-slate-500">—</span>
        ),
      sortAccessor: (r) => r.outcome || "",
    },
    {
      key: "realized_pnl",
      header: "Realized PnL",
      cell: (r) =>
        r.realized_pnl != null ? <code className="text-xs">{r.realized_pnl}</code> : <span className="text-slate-400 dark:text-slate-500">—</span>,
      sortAccessor: (r) => r.realized_pnl || "",
    },
    {
      key: "finalized",
      header: "Finalized",
      cell: (r) => <Chip tone={r.finalized ? "emerald" : "slate"}>{r.finalized ? "yes" : "no"}</Chip>,
      sortAccessor: (r) => (r.finalized ? 1 : 0),
    },
    {
      key: "finalized_at",
      header: "Time",
      cell: (r) => fmtDateTime(r.finalized_at),
      sortAccessor: (r) => r.finalized_at || "",
    },
  ];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Trade Journal</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          GET /journal/entries/ · read-only · requires <code>?account_id=&lt;uuid&gt;</code>
        </p>
      </div>
      {state === "error" && error && <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>}
      <Card>
        {state === "loading" ? (
          <DataTable columns={columns} rows={[]} loading rowKey={(_, i) => String(i)} />
        ) : rows.length === 0 ? (
          <EmptyState title="No journal entries" description="Pass ?account_id=<uuid> to load entries." />
        ) : (
          <DataTable
            columns={columns}
            rows={rows}
            rowKey={(r) => r.correlation_id}
            initialSortKey="finalized_at"
            initialSortDir="desc"
          />
        )}
      </Card>
    </div>
  );
}

function JournalDetail({ correlationId }: { correlationId: string }) {
  const { data, state, error, refetch } = useFetch(() => getJournalEntry(correlationId), [correlationId]);

  return (
    <div className="space-y-4">
      <Breadcrumbs
        items={[
          { label: "Journal", to: "/journal" },
          { label: correlationId.slice(0, 8) },
        ]}
      />
      <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Journal entry</h1>
      {state === "loading" && <Card><div className="h-24 bg-slate-100 dark:bg-slate-800 rounded animate-pulse" /></Card>}
      {state === "error" && error && <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>}
      {state === "empty" && <Card><EmptyState title="Entry not found" /></Card>}
      {state === "success" && data && (
        <Card title="Entry">
          <dl className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
            <KV k="Correlation ID" v={<code className="text-xs">{data.correlation_id}</code>} />
            <KV k="Account ID" v={<code className="text-xs">{data.account_id}</code>} />
            <KV k="Symbol" v={data.signal_snapshot?.symbol || "—"} />
            <KV k="Decision" v={data.decision_snapshot?.decision || "—"} />
            <KV k="Outcome" v={data.outcome || "—"} />
            <KV k="Realized PnL" v={data.realized_pnl != null ? <code className="text-xs">{data.realized_pnl}</code> : "—"} />
            <KV k="Finalized" v={String(data.finalized)} />
            <KV k="Finalized at" v={fmtDateTime(data.finalized_at)} />
            <KV k="Position ID" v={data.position_id ? <code className="text-xs">{data.position_id}</code> : "—"} />
          </dl>
          {data.signal_snapshot && (
            <div className="mt-4 pt-4 border-t border-slate-200 dark:border-slate-800">
              <div className="text-xs text-slate-500 dark:text-slate-400 mb-1">Signal snapshot</div>
              <pre className="text-xs text-slate-700 dark:text-slate-300 bg-slate-50 dark:bg-slate-950 p-3 rounded-md overflow-x-auto tv-scrollbar">
                {JSON.stringify(data.signal_snapshot, null, 2)}
              </pre>
            </div>
          )}
          {data.decision_snapshot && (
            <div className="mt-4 pt-4 border-t border-slate-200 dark:border-slate-800">
              <div className="text-xs text-slate-500 dark:text-slate-400 mb-1">Decision snapshot</div>
              <pre className="text-xs text-slate-700 dark:text-slate-300 bg-slate-50 dark:bg-slate-950 p-3 rounded-md overflow-x-auto tv-scrollbar">
                {JSON.stringify(data.decision_snapshot, null, 2)}
              </pre>
            </div>
          )}
          {Array.isArray(data.order_events) && data.order_events.length > 0 && (
            <div className="mt-4 pt-4 border-t border-slate-200 dark:border-slate-800">
              <div className="text-xs text-slate-500 dark:text-slate-400 mb-1">Order events ({data.order_events.length})</div>
              <div className="space-y-2">
                {data.order_events.map((e) => (
                  <div key={e.event_id} className="text-xs bg-slate-50 dark:bg-slate-950 p-2 rounded">
                    <div className="text-slate-500 dark:text-slate-400">
                      {e.event_type} · <code>{e.event_id.slice(0, 8)}</code> · {fmtDateTime(e.occurred_at)}
                    </div>
                    <pre className="text-slate-700 dark:text-slate-300 mt-1 overflow-x-auto tv-scrollbar">
                      {JSON.stringify(e.payload, null, 2)}
                    </pre>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>
      )}
      <Link to="/journal" className="text-sm text-indigo-600 underline">← Back to journal</Link>
    </div>
  );
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-slate-500 dark:text-slate-400">{k}</dt>
      <dd className="text-sm text-slate-900 dark:text-slate-100 mt-0.5">{v || "—"}</dd>
    </div>
  );
}
