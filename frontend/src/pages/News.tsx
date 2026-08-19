// News Feed — GET /api/v1/news/. Read-only ingested headlines + provider
// sentiment (NEWS-FEED-1). VERIFIED against the backend.
// - sentiment_score is a string (Decimal) or null; null → `--` (provider
//   returned none; ADR-029 keeps sentiment_label null and renders `--`).
// - Optional ?symbol= filter + paginated envelope (PAGE_SIZE=20).

import { useState } from "react";
import { useFetch, isEmptyPaginated } from "@/hooks/useFetch";
import { getNews } from "@/api/news";
import { Button, Card, Alert, EmptyState, Chip } from "@/components";
import { DataTable, type Column } from "@/components/DataTable";
import { fmtDateTime } from "@/lib/time";
import type { NewsItem } from "@/types/news";

function sentimentTone(score: string | null): "emerald" | "rose" | "slate" {
  if (score === null) return "slate";
  const value = parseFloat(score);
  if (value >= 0.25) return "emerald";
  if (value <= -0.25) return "rose";
  return "slate";
}

export function News() {
  const [symbol, setSymbol] = useState("");
  const [page, setPage] = useState(1);

  const { data, state, error, refetch } = useFetch(
    () => getNews({ symbol: symbol.trim() || undefined, page }),
    [symbol, page],
    { isEmpty: isEmptyPaginated }
  );

  const columns: Column<NewsItem>[] = [
    {
      key: "source",
      header: "Source",
      cell: (r) => (r.source ? <Chip tone="blue">{r.source}</Chip> : "—"),
      sortAccessor: (r) => r.source || "",
    },
    {
      key: "headline",
      header: "Headline",
      cell: (r) => (
        <div className="min-w-0">
          <a
            href={r.url || "#"}
            target="_blank"
            rel="noreferrer"
            className="text-sm text-slate-800 hover:text-indigo-600 hover:underline"
          >
            {r.headline || "—"}
          </a>
          {r.body ? (
            <p className="text-xs text-slate-500 mt-0.5 truncate">{r.body}</p>
          ) : null}
        </div>
      ),
      sortAccessor: (r) => r.headline || "",
    },
    {
      key: "symbols",
      header: "Symbols",
      cell: (r) =>
        r.symbols && r.symbols.length > 0 ? (
          <div className="flex flex-wrap gap-1">
            {r.symbols.slice(0, 3).map((s) => (
              <Chip key={s} tone="violet">{s}</Chip>
            ))}
          </div>
        ) : (
          "—"
        ),
    },
    {
      key: "sentiment_score",
      header: "Sentiment",
      cell: (r) =>
        r.sentiment_score !== null && r.sentiment_score !== undefined ? (
          <Chip tone={sentimentTone(r.sentiment_score)}>{r.sentiment_score}</Chip>
        ) : (
          <span className="text-slate-400">--</span>
        ),
      sortAccessor: (r) => (r.sentiment_score ? parseFloat(r.sentiment_score) : -99),
    },
    {
      key: "published_at",
      header: "Published",
      cell: (r) => fmtDateTime(r.published_at),
      sortAccessor: (r) => r.published_at || "",
    },
  ];

  const totalPages = data ? Math.max(1, Math.ceil(data.count / 20)) : 1;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">News Feed</h1>
        <p className="text-sm text-slate-500 mt-1">
          GET /api/v1/news/ · read-only, ingested headlines + provider sentiment
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <input
          value={symbol}
          onChange={(e) => {
            setSymbol(e.target.value);
            setPage(1);
          }}
          placeholder="Filter by symbol (e.g. RELIANCE)"
          className="px-3 py-1.5 text-sm border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500 w-64"
        />
        {data && (
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Prev
            </Button>
            <span className="text-xs text-slate-500">
              Page {page} of {totalPages} · {data.count} items
            </span>
            <Button
              variant="secondary"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        )}
      </div>

      {state === "error" && error && (
        <Alert tone="error" code={error.code} onRetry={refetch}>
          {error.message}
        </Alert>
      )}

      <Card>
        {state === "loading" ? (
          <DataTable columns={columns} rows={[]} loading rowKey={(_, i) => String(i)} />
        ) : state === "empty" || !data || data.results.length === 0 ? (
          <EmptyState
            title={symbol ? `No news for ${symbol}` : "No news ingested yet"}
          />
        ) : (
          <DataTable
            columns={columns}
            rows={data.results}
            rowKey={(r) => r.id}
            initialSortKey="published_at"
            initialSortDir="desc"
          />
        )}
      </Card>
    </div>
  );
}
