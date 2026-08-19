// Watchlist — GET /watchlist/ + DELETE /:instrument_token/.
// Per decision #7: only GET/DELETE. PATCH deferred until verified.

import { useState } from "react";
import { useFetch } from "@/hooks/useFetch";
import { getWatchlist, deleteWatchlistItem } from "@/api/secondary";
import { Card, Alert, EmptyState, Chip, Button } from "@/components";
import { DataTable, type Column } from "@/components/DataTable";
import { fmtDateTime } from "@/lib/time";
import type { WatchlistItem } from "@/types/secondary";
import type { NormalizedApiError } from "@/types/common";

export function Watchlist() {
  const { data, state, error, refetch, setData } = useFetch(getWatchlist);
  const [deleteTarget, setDeleteTarget] = useState<WatchlistItem | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<NormalizedApiError | null>(null);

  const rows: WatchlistItem[] = Array.isArray(data) ? data : data?.results || [];

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteWatchlistItem(deleteTarget.instrument_token);
      // Optimistically remove from list.
      if (data) {
        if (Array.isArray(data)) {
          setData(data.filter((r) => r.instrument_token !== deleteTarget.instrument_token));
        } else {
          setData({ ...data, results: data.results.filter((r) => r.instrument_token !== deleteTarget.instrument_token) });
        }
      }
      setDeleteTarget(null);
    } catch (err) {
      setDeleteError(err as NormalizedApiError);
    } finally {
      setDeleting(false);
    }
  }

  const columns: Column<WatchlistItem>[] = [
    { key: "instrument_token", header: "Token", cell: (r) => <code className="text-[10px]">{r.instrument_token}</code>, sortAccessor: (r) => r.instrument_token },
    { key: "tradingsymbol", header: "Trading symbol", cell: (r) => <span className="font-medium">{r.tradingsymbol || r.symbol || "—"}</span>, sortAccessor: (r) => r.tradingsymbol || r.symbol || "" },
    { key: "exchange", header: "Exchange", cell: (r) => r.exchange ? <Chip tone="blue">{r.exchange}</Chip> : "—" },
    { key: "name", header: "Name", cell: (r) => r.name || "—" },
    { key: "segment", header: "Segment", cell: (r) => r.segment || "—" },
    { key: "instrument_type", header: "Type", cell: (r) => r.instrument_type || "—" },
    { key: "added_at", header: "Added", cell: (r) => fmtDateTime(r.added_at), sortAccessor: (r) => r.added_at || "" },
    {
      key: "actions",
      header: "Actions",
      cell: (r) => <Button variant="danger" onClick={() => setDeleteTarget(r)}>Remove</Button>,
    },
  ];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Watchlist</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          GET /watchlist/ · DELETE /:instrument_token/ ·{" "}
          <span className="text-amber-700">PATCH deferred (contract not verified)</span>
        </p>
      </div>
      <Alert tone="warning" title="⚠ Body + PATCH not verified">
        Body shape not verified. Watchlist item PATCH contract is unverified;
        the UI supports only GET/DELETE for now. PATCH will be added once the
        request schema is confirmed.
      </Alert>
      {state === "error" && error && <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>}
      <Card>
        {state === "loading" ? (
          <DataTable columns={columns} rows={[]} loading rowKey={(_, i) => String(i)} />
        ) : rows.length === 0 ? (
          <EmptyState title="No watchlist items" />
        ) : (
          <DataTable columns={columns} rows={rows} rowKey={(r) => String(r.instrument_token)} initialSortKey="tradingsymbol" />
        )}
      </Card>

      {deleteTarget && (
        <div className="fixed inset-0 bg-slate-900/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-slate-900 rounded-lg shadow-xl max-w-md w-full p-6 space-y-4">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Remove from watchlist?</h2>
            <p className="text-sm text-slate-600 dark:text-slate-400">
              Remove <span className="font-medium">{deleteTarget.tradingsymbol || deleteTarget.symbol || deleteTarget.instrument_token}</span> from your watchlist?
            </p>
            {deleteError && <Alert tone="error" code={deleteError.code}>{deleteError.message}</Alert>}
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => { setDeleteTarget(null); setDeleteError(null); }} disabled={deleting}>Cancel</Button>
              <Button variant="danger" loading={deleting} onClick={confirmDelete}>Confirm remove</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
