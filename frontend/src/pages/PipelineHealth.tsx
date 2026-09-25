// PipelineHealth — GET /pipeline-health/.
// Also runs the unauthenticated /api/v1/health/ component checks for
// liveness/db/cache/celery/eventbus/system.

import { useFetch } from "@/hooks/useFetch";
import { getPipelineHealth, getHealthRoot, getHealthComponent } from "@/api/system";
import { Card, Alert, EmptyState, Chip } from "@/components";
import { useEffect, useState } from "react";
import type { HealthCheck } from "@/api/system";
import { fmtDateTime } from "@/lib/time";

export function PipelineHealth() {
  const { data, state, error, refetch } = useFetch(getPipelineHealth);
  const [checks, setChecks] = useState<HealthCheck[]>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const components = ["db", "cache", "celery", "eventbus", "system"];
      const all: HealthCheck[] = [];
      const root = await getHealthRoot();
      all.push(root);
      for (const c of components) {
        const chk = await getHealthComponent(c);
        all.push(chk);
      }
      if (!cancelled) setChecks(all);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Pipeline Health</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">GET /pipeline-health/ + GET /health/*</p>
      </div>
      <Alert tone="warning" title="⚠ /pipeline-health/ body not verified">
        Defensive rendering for pipeline-health; health/* endpoints are unauthenticated.
      </Alert>

      <Card title="Health component checks" description="GET /api/v1/health/ + /health/<name>/">
        {checks.length === 0 ? (
          <div className="text-sm text-slate-500 dark:text-slate-400 italic">Running checks…</div>
        ) : (
          <ul className="divide-y divide-slate-100">
            {checks.map((c) => (
              <li key={c.name} className="py-2 flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-medium text-slate-900 dark:text-slate-100">{c.name}</div>
                  {c.raw !== null && c.raw !== undefined && (
                    <pre className="text-[10px] text-slate-500 dark:text-slate-400 mt-1 max-h-20 overflow-y-auto tv-scrollbar">
                      {JSON.stringify(c.raw, null, 2)}
                    </pre>
                  )}
                </div>
                <Chip tone={c.status === "ok" ? "emerald" : c.status === "fail" ? "rose" : "amber"}>
                  {c.status}
                </Chip>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {state === "error" && error && <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>}
      <Card title="Pipeline status" description="GET /pipeline-health/">
        {state === "loading" ? (
          <div className="h-24 bg-slate-100 dark:bg-slate-800 rounded animate-pulse" />
        ) : state === "empty" || !data ? (
          <EmptyState title="No pipeline health data" />
        ) : (
          <div className="space-y-4">
            <dl className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
              <KV
                k="Overall"
                v={
                  <Chip tone={(data.snapshot?.overall_status || data.status) === "ok" ? "emerald" : (data.snapshot?.overall_status || data.status) === "degraded" ? "amber" : "rose"}>
                    {(data.snapshot?.overall_status || data.status) ?? "—"}
                  </Chip>
                }
              />
              <KV k="Evaluated at" v={fmtDateTime(data.snapshot?.evaluated_at || data.last_run_at)} />
              {data.snapshot?.stage_statuses && (
                <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-xs">
                  {Object.entries(data.snapshot.stage_statuses).map(([stage, st]) => (
                    <div key={stage} className="flex items-center justify-between gap-2 rounded-md bg-slate-50 dark:bg-slate-950 px-2 py-1">
                      <span className="text-slate-500 dark:text-slate-400">{stage}</span>
                      <Chip tone={st === "ok" ? "emerald" : st === "degraded" ? "amber" : "rose"}>{st}</Chip>
                    </div>
                  ))}
                </div>
              )}
            </dl>
            {data.heartbeats && data.heartbeats.length > 0 && (
              <div>
                <p className="text-xs text-slate-500 dark:text-slate-400 mb-2">Stage heartbeats</p>
                <ul className="divide-y divide-slate-100 rounded-md border border-slate-200 dark:border-slate-800">
                  {data.heartbeats.map((hb) => (
                    <li key={`${hb.stage}-${hb.symbol_scope}`} className="px-3 py-2 flex items-center justify-between gap-3 text-sm">
                      <span className="font-medium text-slate-900 dark:text-slate-100">{hb.stage}</span>
                      <span className="text-xs text-slate-500 dark:text-slate-400">{hb.symbol_scope} · {fmtDateTime(hb.last_event_at)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </Card>
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
