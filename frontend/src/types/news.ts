// News Feed (NEWS-FEED-1) — /api/v1/news/.
// VERIFIED against the backend (2026-08-17): paginated envelope {count,next,
// previous,results}, sentiment_score is a string or null, sentiment_label is
// always null in this batch (render `--`), body is a string or "".

export interface NewsItem {
  id: string;
  source: string;
  headline: string;
  body: string;
  url: string;
  published_at: string;
  ingested_at: string;
  symbols: string[];
  sentiment_score: string | null;
  sentiment_label: string | null;
  [key: string]: unknown;
}
