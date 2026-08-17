// Rule Engine API module — read-only per the contract.
// SOURCE: 04_API_CONTRACT.md — /api/v1/rule-engine/.
// ⚠ configs/ and executions/ return BARE arrays (not paginated) — VERIFIED 2026-08-17.

import { apiGet } from "./client";
import type { RuleConfig, RuleExecution } from "@/types/rules";

export function getRuleConfigs(): Promise<RuleConfig[]> {
  return apiGet<RuleConfig[]>("/rule-engine/configs/");
}

export function getRuleConfig(ruleId: string): Promise<RuleConfig> {
  return apiGet<RuleConfig>(`/rule-engine/configs/${encodeURIComponent(ruleId)}/`);
}

export function getRuleExecutions(): Promise<RuleExecution[]> {
  return apiGet<RuleExecution[]>("/rule-engine/executions/");
}
