// Rules — GET /rule-engine/configs/.
// ⚠ Body NOT VERIFIED — may be paginated or bare list. RuleConfig fields VERIFIED.

import { useFetch } from "@/hooks/useFetch";
import { getRuleConfigs } from "@/api/rules";
import { Card, Alert, EmptyState, Chip, gateTone } from "@/components";
import { DataTable, type Column } from "@/components/DataTable";
import { useNavigate } from "react-router-dom";
import type { RuleConfig } from "@/types/rules";

export function Rules() {
  const { data, state, error, refetch } = useFetch(getRuleConfigs);
  const navigate = useNavigate();

  // Normalize: data may be an array or a paginated envelope.
  const rows: RuleConfig[] = Array.isArray(data) ? data : data?.results || [];

  const columns: Column<RuleConfig>[] = [
    { key: "rule_id", header: "Rule ID", cell: (r) => <span className="font-medium">{r.rule_id}</span>, sortAccessor: (r) => r.rule_id },
    {
      key: "enabled",
      header: "Enabled",
      cell: (r) => <Chip tone={r.enabled ? "emerald" : "slate"}>{r.enabled ? "enabled" : "disabled"}</Chip>,
      sortAccessor: (r) => (r.enabled ? 1 : 0),
    },
    {
      key: "severity_override",
      header: "Severity",
      cell: (r) => (r.severity_override ? <Chip tone="amber">{r.severity_override}</Chip> : <span className="text-slate-400 text-xs">default</span>),
      sortAccessor: (r) => r.severity_override || "",
    },
    {
      key: "validated_regimes",
      header: "ADR-029 gate (regimes)",
      cell: (r) => <RegimeChips regimes={r.validated_regimes} />,
    },
    {
      key: "parameters",
      header: "Parameters",
      cell: (r) => (
        <code className="text-[10px] text-slate-500 truncate inline-block max-w-xs">
          {Object.keys(r.parameters || {}).length > 0 ? JSON.stringify(r.parameters) : "{}"}
        </code>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Rule Configs</h1>
        <p className="text-sm text-slate-500 mt-1">
          GET /rule-engine/configs/ · Read-only (no config-write contract exists)
        </p>
      </div>
      <Alert tone="warning" title="⚠ Contract not verified">
        Body shape not verified. May be paginated or bare list.
      </Alert>
      {state === "error" && error && (
        <Alert tone="error" code={error.code} onRetry={refetch}>{error.message}</Alert>
      )}
      <Card>
        {state === "loading" ? (
          <DataTable columns={columns} rows={[]} loading rowKey={(_, i) => String(i)} />
        ) : rows.length === 0 ? (
          <EmptyState title="No rule configs" description="No RuleConfig records returned." />
        ) : (
          <DataTable
            columns={columns}
            rows={rows}
            rowKey={(r) => r.rule_id}
            onRowClick={(r) => navigate(`/rules/${r.rule_id}`)}
            initialSortKey="rule_id"
          />
        )}
      </Card>
      <p className="text-xs text-slate-500">
        ADR-029 gate colors: <Chip tone="emerald">GO</Chip> <Chip tone="rose">NO_GO</Chip> <Chip tone="amber">INSUFFICIENT_DATA</Chip>
      </p>
    </div>
  );
}

function RegimeChips({ regimes }: { regimes: Record<string, string> }) {
  const entries = Object.entries(regimes || {});
  if (entries.length === 0) {
    return <span className="text-xs text-slate-400">no regimes</span>;
  }
  return (
    <div className="flex flex-wrap gap-1">
      {entries.map(([regime, status]) => (
        <span key={regime} className="inline-flex items-center gap-1">
          <span className="text-[10px] text-slate-600">{regime}</span>
          <Chip tone={gateTone(status)}>{status}</Chip>
        </span>
      ))}
    </div>
  );
}
