// TradeExportStatus — GET /dashboard/trades/history/export/:id/.
// Verified against backend ExportJobSerializer: polls status, renders a
// download link only when file_url is present in the response.

import { useParams, Link } from "react-router-dom";
import { usePoll } from "@/hooks/usePoll";
import { getTradeExportStatus } from "@/api/dashboard";
import { Card, Alert, Breadcrumbs, Button, Chip } from "@/components";
import { fmtDateTime } from "@/lib/time";
import { Download, RefreshCw } from "lucide-react";
import type { ExportJob } from "@/types/dashboard";

export function TradeExportStatus() {
  const { id } = useParams<{ id: string }>();
  const { data, error, polling } = usePoll<ExportJob>(
    () => getTradeExportStatus(id || ""),
    [id],
    {
      shouldStop: (d) => d?.status === "COMPLETED" || d?.status === "FAILED",
      intervalMs: 3000,
      timeoutMs: 5 * 60 * 1000,
    }
  );

  return (
    <div className="space-y-4">
      <Breadcrumbs
        items={[
          { label: "Trades", to: "/trades" },
          { label: "Export" },
          { label: id?.slice(0, 8) || "—" },
        ]}
      />
      <div className="flex items-baseline justify-between">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Trade export</h1>
        {polling && (
          <span className="text-xs text-slate-500 dark:text-slate-400 flex items-center gap-1">
            <RefreshCw className="w-3 h-3 animate-spin" />
            Polling…
          </span>
        )}
      </div>

      {error && !data && (
        <Alert tone="error" code={error.code}>
          {error.message || "Failed to load export status."}
        </Alert>
      )}

      {!data && !error && (
        <Card>
          <div className="h-24 bg-slate-100 dark:bg-slate-800 rounded animate-pulse" />
        </Card>
      )}

      {data && (
        <Card title="Export job">
          <dl className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
            <KV k="Job ID" v={<code className="text-xs">{data.export_id}</code>} />
            <KV k="Status" v={<Chip tone={data.status === "COMPLETED" ? "emerald" : data.status === "FAILED" ? "rose" : "amber"}>{data.status || "—"}</Chip>} />
            <KV k="Format" v={data.format || "—"} />
            <KV k="Requested" v={fmtDateTime(data.requested_at)} />
            <KV k="Completed" v={fmtDateTime(data.completed_at)} />
            {data.error_message && <KV k="Error" v={<span className="text-rose-700">{data.error_message}</span>} />}
          </dl>

          {data.file_url ? (
            <div className="mt-4 pt-4 border-t border-slate-200 dark:border-slate-800">
              <p className="text-xs text-slate-600 dark:text-slate-400 mb-2">
                Download is available. Click below to retrieve the file.
              </p>
              <a href={data.file_url} target="_blank" rel="noopener noreferrer">
                <Button variant="primary">
                  <Download className="w-4 h-4" />
                  Download export
                </Button>
              </a>
            </div>
          ) : (
            <div className="mt-4 pt-4 border-t border-slate-200 dark:border-slate-800">
              <p className="text-xs text-slate-500 dark:text-slate-400 italic">
                No download URL provided in the response. If the status is
                COMPLETED but no URL appears, the backend may use a different
                delivery mechanism (e.g. async email) or the job is still
                pending.
              </p>
            </div>
          )}
        </Card>
      )}

      <Alert tone="info" title="Contract note">
        Export jobs are created via POST (async) and polled here until
        COMPLETED/FAILED. The download link renders only if the response
        supplies a <code className="text-[10px]">file_url</code>.
      </Alert>

      <Link to="/trades" className="text-sm text-indigo-600 underline">← Back to trades</Link>
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
