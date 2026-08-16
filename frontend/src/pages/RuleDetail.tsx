// RuleDetail — GET /rule-engine/configs/:ruleId/.

import { useParams, Link } from "react-router-dom";
import { useFetch } from "@/hooks/useFetch";
import { getRuleConfig } from "@/api/rules";
import { Card, Alert, Breadcrumbs, EmptyState, Chip, gateTone } from "@/components";

export function RuleDetail() {
  const { ruleId } = useParams<{ ruleId: string }>();
  const { data, state, error, refetch } = useFetch(() => getRuleConfig(ruleId || ""), [ruleId]);

  return (
    <div className="space-y-4">
      <Breadcrumbs
        items={[
          { label: "Rules", to: "/rules" },
          { label: ruleId || "—" },
        ]}
      />
      <h1 className="text-2xl font-bold text-slate-900">Rule — {ruleId}</h1>

      {state === "loading" && <Card><div className="h-24 bg-slate-100 rounded animate-pulse" /></Card>}
      {state === "error" && error && <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>}
      {state === "empty" && <Card><EmptyState title="Rule not found" /></Card>}

      {state === "success" && data && (
        <div className="space-y-4">
          <Card title="Configuration">
            <dl className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
              <KV k="Rule ID" v={<Chip tone="violet">{data.rule_id}</Chip>} />
              <KV k="Enabled" v={<Chip tone={data.enabled ? "emerald" : "slate"}>{String(data.enabled)}</Chip>} />
              <KV k="Severity override" v={data.severity_override ? <Chip tone="amber">{data.severity_override}</Chip> : <span className="text-slate-400 text-xs">default</span>} />
            </dl>
          </Card>

          <Card title="ADR-029 validation gate" description="validated_regimes (RuleValidationService per regime)">
            {Object.keys(data.validated_regimes || {}).length === 0 ? (
              <EmptyState title="No validated regimes" description="This rule has not been validated against any regime yet." />
            ) : (
              <div className="overflow-x-auto tv-scrollbar">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-xs text-slate-500">
                      <th className="px-3 py-2 text-left font-semibold">Regime</th>
                      <th className="px-3 py-2 text-left font-semibold">Gate status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(data.validated_regimes).map(([regime, status]) => (
                      <tr key={regime} className="border-b border-slate-100">
                        <td className="px-3 py-2">{regime}</td>
                        <td className="px-3 py-2"><Chip tone={gateTone(status)}>{status}</Chip></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card title="Parameters" description="parameters (JSON)">
            <pre className="text-xs text-slate-700 bg-slate-50 p-3 rounded-md overflow-x-auto tv-scrollbar">
              {JSON.stringify(data.parameters || {}, null, 2)}
            </pre>
          </Card>

          <Link to="/rules" className="text-sm text-indigo-600 underline">← Back to rules</Link>
        </div>
      )}
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
