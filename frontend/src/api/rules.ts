// Rule Engine API module — read-only per the contract.
// SOURCE: 04_API_CONTRACT.md — /api/v1/rule-engine/.

import { apiGet, apiGetPaged } from "./client";
import type { Paginated } from "@/types/common";
import type { RuleConfig, RuleExecution } from "@/types/rules";

export function getRuleConfigs(): Promise<Paginated<RuleConfig> | RuleConfig[]> {
  // ⚠ Body NOT VERIFIED — may be paginated or bare list. Try both.
  return apiGet<unknown>("/rule-engine/configs/").then((res) => {
    if (Array.isArray(res)) return res as RuleConfig[];
    if (res && typeof res === "object" && "results" in res) {
      return res as Paginated<RuleConfig>;
    }
    return [];
  });
}

export function getRuleConfig(ruleId: string): Promise<RuleConfig> {
  return apiGet<RuleConfig>(`/rule-engine/configs/${encodeURIComponent(ruleId)}/`);
}

export function getRuleExecutions(): Promise<Paginated<RuleExecution> | RuleExecution[]> {
  return apiGet<unknown>("/rule-engine/executions/").then((res) => {
    if (Array.isArray(res)) return res as RuleExecution[];
    if (res && typeof res === "object" && "results" in res) {
      return res as Paginated<RuleExecution>;
    }
    return [];
  });
}

// Unused import silencer.
void apiGetPaged;
