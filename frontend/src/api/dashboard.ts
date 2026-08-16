// Dashboard (trading_core) API module.
// SOURCE: 04_API_CONTRACT.md — /api/v1/dashboard/.

import { apiGet, apiGetPaged, apiPost } from "./client";
import type { Paginated } from "@/types/common";
import type {
  DashboardHomeSummary,
  ExportJob,
  Holding,
  OrderSnapshot,
  PortfolioComposition,
  PositionSnapshot,
  TradeRecord,
} from "@/types/dashboard";

export function getHomeSummary(): Promise<DashboardHomeSummary> {
  return apiGet<DashboardHomeSummary>("/dashboard/home/summary/");
}

export function getPortfolioComposition(): Promise<PortfolioComposition> {
  return apiGet<PortfolioComposition>("/dashboard/portfolio/composition/");
}

export function getHolding(symbol: string): Promise<Holding> {
  return apiGet<Holding>(`/dashboard/portfolio/holdings/${encodeURIComponent(symbol)}/`);
}

export function getLivePositions(): Promise<Paginated<PositionSnapshot>> {
  return apiGetPaged<PositionSnapshot>("/dashboard/positions/live/");
}

export function getLivePosition(id: string): Promise<PositionSnapshot> {
  return apiGet<PositionSnapshot>(`/dashboard/positions/live/${encodeURIComponent(id)}/`);
}

export function getOrders(): Promise<Paginated<OrderSnapshot>> {
  return apiGetPaged<OrderSnapshot>("/dashboard/orders/");
}

export function getOrder(id: string): Promise<OrderSnapshot> {
  return apiGet<OrderSnapshot>(`/dashboard/orders/${encodeURIComponent(id)}/`);
}

export function getTradeHistory(): Promise<Paginated<TradeRecord>> {
  return apiGetPaged<TradeRecord>("/dashboard/trades/history/");
}

export function getOpenTrades(): Promise<Paginated<TradeRecord>> {
  return apiGetPaged<TradeRecord>("/dashboard/trades/open/");
}

export function getClosedTrades(): Promise<Paginated<TradeRecord>> {
  return apiGetPaged<TradeRecord>("/dashboard/trades/closed/");
}

/** Verified against backend: POST creates an export job, 202 + ExportJobSerializer. */
export function requestTradeExport(): Promise<ExportJob> {
  return apiPost<ExportJob>("/dashboard/trades/history/export/", { format: "csv" });
}

export function getTradeExportStatus(id: string): Promise<ExportJob> {
  return apiGet<ExportJob>(`/dashboard/trades/history/export/${encodeURIComponent(id)}/`);
}
