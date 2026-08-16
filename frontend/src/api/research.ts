// Research / Backtesting API module.
// SOURCE: 04_API_CONTRACT.md — /api/v1/backtesting/. All shapes VERIFIED.
//
// Per 08 rule 5: never auto-retry POSTs. Sync endpoints (walk-forward/edge/cost)
// may take a long time; callers set their own timeout/retry UX.
//
// Per decision #10: 120s client timeout for sync research POSTs.

import { apiGet, apiPost } from "./client";
import type {
  BacktestRunCreateRequest,
  BacktestRunCreated,
  BacktestRunDetail,
  CostSensitivityRequest,
  CostSensitivityResponse,
  EdgeValidationRequest,
  EdgeValidationResponse,
  WalkForwardRequest,
  WalkForwardResponse,
} from "@/types/research";

export function createBacktestRun(body: BacktestRunCreateRequest): Promise<BacktestRunCreated> {
  return apiPost<BacktestRunCreated>("/backtesting/runs/", body);
}

export function getBacktestRun(id: string): Promise<BacktestRunDetail> {
  return apiGet<BacktestRunDetail>(`/backtesting/runs/${encodeURIComponent(id)}/`);
}

export function runWalkForward(body: WalkForwardRequest): Promise<WalkForwardResponse> {
  return apiPost<WalkForwardResponse>("/backtesting/walk-forward/", body);
}

export function runEdgeValidation(body: EdgeValidationRequest): Promise<EdgeValidationResponse> {
  return apiPost<EdgeValidationResponse>("/backtesting/edge-validation/", body);
}

export function runCostSensitivity(body: CostSensitivityRequest): Promise<CostSensitivityResponse> {
  return apiPost<CostSensitivityResponse>("/backtesting/cost-sensitivity/", body);
}

/** Fetch with a 120s timeout — used by sync research POSTs. */
export async function withTimeout<T>(
  promise: Promise<T>,
  timeoutMs = 120_000
): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | null = null;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(
      () =>
        reject({
          isEnvelope: false,
          code: "client_timeout",
          message: "The server is still computing. Retry once ready.",
          status: null,
          isNetwork: false,
        }),
      timeoutMs
    );
  });
  try {
    return await Promise.race([promise, timeout]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}
