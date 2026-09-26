// Strategy Registry API — /api/v1/strategies/.
// VERIFIED against backend 2026-09-25: list (bare array, sorted by priority),
// create 201, detail, PATCH, soft-delete 204.

import { apiGet, apiDelete, apiPost, apiPatch } from "./client";
import type { TradingStrategy, TradingStrategyPayload, StrategySymbolAffinity } from "@/types/strategies";

export function getStrategies(): Promise<TradingStrategy[]> {
  return apiGet<TradingStrategy[]>("/strategies/");
}

export function getStrategyAffinities(symbol?: string): Promise<StrategySymbolAffinity[]> {
  const query = symbol ? `?symbol=${encodeURIComponent(symbol)}` : "";
  return apiGet<StrategySymbolAffinity[]>(`/strategies/affinities/${query}`);
}

export function getStrategy(id: string): Promise<TradingStrategy> {
  return apiGet<TradingStrategy>(`/strategies/${encodeURIComponent(id)}/`);
}

export function createStrategy(payload: TradingStrategyPayload): Promise<TradingStrategy> {
  return apiPost<TradingStrategy>("/strategies/", payload);
}

export function updateStrategy(id: string, payload: Partial<TradingStrategyPayload>): Promise<TradingStrategy> {
  return apiPatch<TradingStrategy>(`/strategies/${encodeURIComponent(id)}/`, payload);
}

export function deleteStrategy(id: string): Promise<void> {
  return apiDelete<void>(`/strategies/${encodeURIComponent(id)}/`);
}