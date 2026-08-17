// News Feed API module — NEWS-FEED-1.
// SOURCE: 04_API_CONTRACT.md — /api/v1/news/. All shapes VERIFIED.
// Read-only ingested headlines + provider sentiment. Paginated envelope.

import { apiGetPaged } from "./client";
import type { Paginated } from "@/types/common";
import type { NewsItem } from "@/types/news";

export function getNews(
  params: { symbol?: string; page?: number } = {}
): Promise<Paginated<NewsItem>> {
  const search = new URLSearchParams();
  if (params.symbol) search.set("symbol", params.symbol);
  if (params.page) search.set("page", String(params.page));
  const qs = search.toString();
  return apiGetPaged<NewsItem>(`/news/${qs ? `?${qs}` : ""}`);
}
