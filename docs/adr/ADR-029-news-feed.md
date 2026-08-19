# ADR-029: News Feed — licensed provider ingestion (NEWS-FEED-1)

**Status:** Proposed
**Date:** 2026-08-17
**Deciders:** Trading Core team (user + architect)
**Depends on:** ADR-002 (event-driven architecture), ADR-013 (event-bus streams)

## Context

`apps/news_feed` was scaffolded but left deliberately empty pending a ToS review
of scraping NSE/BSE/Moneycontrol (see the comment in
`apps/intelligence/infrastructure/trading_signal_bridge.py:148` and
`ta_completed_handler.py:303`). `NEWS_API_KEY` / `NEWS_API_BASE_URL` already
exist in `.env.example` but nothing reads them.

The intelligence layer needs a news dimension: the `NewsContext` / `NewsItem`
dataclasses in `core/events/event_types.py` exist and `IntelligencePacket`
carries `news_context`, but every packet is currently assembled with the
unchecked `NewsContext()` default and the absence is tagged
`missing: ["news"]`.

## Decision

### 1. Provider: **Marketaux** (`api.marketaux.com`), never NSE/BSE/Moneycontrol scraping

Direct scraping of exchange/market-web sites was ruled out by the ToS review
(the scaffold comment). Of the India-equities-capable licensed APIs we already
assumed in `.env.example`:

| Provider | India equities | Symbol tagging | Free/sandbox tier | Sentiment in response |
|---|---|---|---|---|
| **Marketaux** | `countries=in` on 200k+ entities | **Native** — `symbols=RELIANCE,TCS`, `entities[].symbol` per article | 100 req/day, 3 articles/req | Yes — `entities[].sentiment_score` (all plans) |
| NewsAPI.org | Partial (keyword/domain search, weak NSE symbols) | No — keyword search only | 100 req/day | No |
| Finnhub | `related` tickers on company news | Partial (`related` string) | 60 req/min | Paid endpoint only |

Marketaux is chosen because its `symbols` query param and per-article
`entities[].symbol` map directly to the `NewsItem.symbols[]` data model and to
the per-symbol `NewsContext` lookup the intelligence bridges need — the other
two require keyword search + local tagging heuristics, which is exactly the
hand-rolled scraping/classification we are avoiding.

### 2. Sentiment: store the provider's score, never fabricate

- `sentiment_score` (nullable Decimal) is persisted **only** when the provider
  returns it (`entities[].sentiment_score`, range −1…+1). No locally-scored
  sentiment is ever invented.
- `sentiment_label` stays `null` and renders `--`: Marketaux does not return a
  label, and mapping score→label ourselves would be a hand-rolled sentiment
  model — explicitly out of scope (a future batch may add a real model).
- When building the packet `NewsContext`, a null score maps to
  `AggregateSentiment.NEUTRAL` (the enum's "no signal" value) and the packet
  `NewsItem.sentiment` is a coarse 4-bucket mapping of the *provider's* score
  (`>= 0.25` POSITIVE, `<= -0.25` NEGATIVE, else NEUTRAL). Materiality is not
  assessed in this batch and is always `LOW` (the dataclass baseline). This is
  a documented integration mapping of a real provider value, not a fabricated
  signal.

### 3. Provider swappable behind a port (same pattern as `BrokerAdapter`)

`apps/news_feed/application/ports.py` defines `NewsProvider` / `NewsItemRepository`
/ `DailyCallBudget` protocols (mirroring `apps/execution/application/ports.py`).
The application services depend only on the protocols; concrete implementations
live in `apps/news_feed/infrastructure/providers/` (`MarketauxNewsProvider`,
`FakeNewsProvider` for tests/local dev) and are wired in `get_ingestion_service()`.
`NEWS_PROVIDER=marketaux|fake` selects the implementation.

### 4. Ingestion cadence and budget

- Beat entry `ingest-news` runs every **`NEWS_POLL_INTERVAL_SECONDS` (default 900s =
  15 min)**. Rationale: this is a paper-trading research tool, not a low-latency
  terminal; 15 min keeps the daily provider quota (100 free-tier requests) within
  budget (96 polls/day) while staying fresher than a daily batch. The interval is
  a setting, not a constant.
- Dedup on `(source, url)` via a unique constraint — re-polling never creates
  duplicate rows.
- Rate limit is read from settings (`NEWS_RATE_LIMIT_CALLS_PER_DAY`, default 100),
  not hardcoded. A `DailyCallBudget` ledger reserves a call before each fetch and
  the task refuses to run once the day's budget is spent (logged, not an error).
  Provider `429`/`402` responses raise `NewsProviderRateLimited`, which the task
  retries with exponential backoff (BaseTask) and, at max retries, logs — it never
  crashes the beat schedule.

### 5. Event surface

Ingestion publishes one `news.NewsIngested` event per stored item
(`{news_id, source, headline, url, published_at, symbols, sentiment_score}`) so
other apps can consume it (the audit log's wildcard subscription records it
automatically). No other app is reached into.

## Consequences

- `apps/news_feed` becomes a full Clean-Architecture app (domain/application/
  infrastructure/interfaces), mounted at `/api/v1/news/`.
- The intelligence bridges (`trading_signal_bridge.py`, `ta_completed_handler.py`)
  replace the `NewsContext()` default with a real per-symbol lookup: a real query
  that finds nothing stays `missing: ["news"]` (legit absence); a query that finds
  items populates the packet and drops the tag. A disabled/absent news store keeps
  the "never checked" semantics.
- Free tier limits ingestion to 3 articles/request; production upgrade path is a
  paid Marketaux tier (10,000 req/day, 50 articles/req) — only settings change
  (`NEWS_RATE_LIMIT_CALLS_PER_DAY`, `NEWS_ARTICLES_PER_REQUEST`).
