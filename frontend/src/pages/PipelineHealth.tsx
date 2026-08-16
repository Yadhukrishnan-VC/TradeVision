// PipelineHealth — GET /pipeline-health/.
// Also runs the unauthenticated /api/v1/health/ component checks for
// liveness/db/cache/celery/eventbus/system.

import { useFetch } from "@/hooks/useFetch";
import { getPipelineHealth, getHealthRoot, getHealthComponent } from "@/api/system";
import { Card, Alert, EmptyState, Chip } from "@/components";
import { useEffect, useState } from "react";
import type { HealthCheck } from "@/api/system";
import { fmtDateTime } from "@/lib/time";
import { toNum, fmtDecimal } from "@/lib/decimal";

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
        <h1 className="text-2xl font-bold text-slate-900">Pipeline Health</h1>
        <p className="text-sm text-slate-500 mt-1">GET /pipeline-health/ + GET /health/*</p>
      </div>
      <Alert tone="warning" title="⚠ /pipeline-health/ body not verified">
        Defensive rendering for pipeline-health; health/* endpoints are unauthenticated.
      </Alert>

      <Card title="Health component checks" description="GET /api/v1/health/ + /health/<name>/">
        {checks.length === 0 ? (
          <div className="text-sm text-slate-500 italic">Running checks…</div>
        ) : (
          <ul className="divide-y divide-slate-100">
            {checks.map((c) => (
              <li key={c.name} className="py-2 flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-medium text-slate-900">{c.name}</div>
                  {c.raw !== null && c.raw !== undefined && (
                    <pre className="text-[10px] text-slate-500 mt-1 max-h-20 overflow-y-auto tv-scrollbar">
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
          <div className="h-24 bg-slate-100 rounded animate-pulse" />
        ) : state === "empty" || !data ? (
          <EmptyState title="No pipeline health data" />
        ) : (
          <dl className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
            <KV k="Status" v={<Chip tone={data.status === "ok" ? "emerald" : data.status === "degraded" ? "amber" : "rose"}>{data.status || "—"}</Chip>} />
            <KV k="Last run" v={fmtDateTime(data.last_run_at)} />
            <KV k="Staleness (s)" v={data.staleness_seconds !== null && data.staleness_seconds !== undefined ? fmtDecimal(data.staleness_seconds, 0) : "—"} />
            {data.components && (
              <div className="md:col-span-3">
                <dt className="text-xs text-slate-500 mb-1">Components</dt>
                <dd>
                  <pre className="text-[10px] text-slate-700 bg-slate-50 p-3 rounded-md overflow-x-auto tv-scrollbar">
                    {JSON.stringify(data.components, null, 2)}
                  </pre>
                </dd>
              </div>
            )}
          </dl>
        )}
      </Card>
    </div>
  );
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-slate-500">{k}</dt>
      <dd className="text-sm text-slate-900 mt-0.5">{v || "—"}</dd>
    </div>
  );
}

void toNum;
