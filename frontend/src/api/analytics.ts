// Analytics & Risk API module (per-account).
// SOURCE: 04_API_CONTRACT.md — /api/v1/dashboard/accounts/:account_id/.
// ⚠ All bodies NOT VERIFIED — defensive interfaces; render whatever keys arrive.

import { apiGet } from "./client";
import type {
  AnalyticsDailyRollup,
  AnalyticsPerformance,
  AnalyticsPnl,
  AnalyticsRiskSummary,
} from "@/types/secondary";

export function getAnalyticsPnl(accountId: string): Promise<AnalyticsPnl> {
  return apiGet<AnalyticsPnl>(`/dashboard/accounts/${encodeURIComponent(accountId)}/pnl`);
}

export function getAnalyticsPnlDaily(accountId: string): Promise<AnalyticsDailyRollup> {
  return apiGet<AnalyticsDailyRollup>(
    `/dashboard/accounts/${encodeURIComponent(accountId)}/pnl/daily`
  );
}

export function getAnalyticsPerformance(accountId: string): Promise<AnalyticsPerformance> {
  return apiGet<AnalyticsPerformance>(
    `/dashboard/accounts/${encodeURIComponent(accountId)}/performance`
  );
}

export function getAnalyticsRisk(accountId: string): Promise<AnalyticsRiskSummary> {
  return apiGet<AnalyticsRiskSummary>(
    `/dashboard/accounts/${encodeURIComponent(accountId)}/risk`
  );
}
