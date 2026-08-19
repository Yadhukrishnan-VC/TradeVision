// Rules — GET /rule-engine/configs/.
// ⚠ Body VERIFIED 2026-08-17: bare array. validated_regimes NOT exposed by the API.

import { useFetch } from "@/hooks/useFetch";
import { getRuleConfigs } from "@/api/rules";
import { Card, Alert, EmptyState, Chip } from "@/components";
import { DataTable, type Column } from "@/components/DataTable";
import { useNavigate } from "react-router-dom";
import type { RuleConfig } from "@/types/rules";

export function Rules() {
  const { data, state, error, refetch } = useFetch(getRuleConfigs);
  const navigate = useNavigate();

  const rows: RuleConfig[] = data || [];

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
      cell: (r) => (r.severity_override ? <Chip tone="amber">{r.severity_override}</Chip> : <span className="text-slate-400 dark:text-slate-500 text-xs">default</span>),
      sortAccessor: (r) => r.severity_override || "",
    },
    {
      key: "validated_regimes",
      header: "ADR-029 gate (regimes)",
      cell: () => <span className="text-slate-400 dark:text-slate-500 text-xs">—</span>,
    },
    {
      key: "parameters",
      header: "Parameters",
      cell: (r) => (
        <code className="text-[10px] text-slate-500 dark:text-slate-400 truncate inline-block max-w-xs">
          {Object.keys(r.parameters || {}).length > 0 ? JSON.stringify(r.parameters) : "{}"}
        </code>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">Rule Configs</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          GET /rule-engine/configs/ · Read-only (no config-write contract exists)
        </p>
      </div>
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
      <p className="text-xs text-slate-500 dark:text-slate-400">
        ADR-029 gate statuses (GO / NO_GO / INSUFFICIENT_DATA) are stored on the model but not exposed by the configs API — column shows —.
      </p>
    </div>
  );
}