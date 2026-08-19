# Edge Validation Report — TradeVision

> **Overall verdict: NO EDGE VERDICT POSSIBLE — prerequisite unmet.**
> The real-data prerequisite for this batch has **not** been satisfied: no real
> (Zerodha) historical data exists in the system, so no rule's edge can be
> validated. Every rule × regime pair is **INSUFFICIENT-DATA**. `RuleConfig`
> `validated_regimes` has been left **completely untouched** — no writes, not
> even placeholder ones.
>
> This batch instead: (a) proves and documents the unmet prerequisite,
> (b) builds and ground-truth-tests the shuffled-baseline significance
> machinery that the real-data run will need, and (c) smoke-runs the existing
> walk-forward / cost-sensitivity / significance pipeline end-to-end on the
> synthetic data — **labeled, not edge evidence** — so the machinery is known to
> execute the moment real data exists.

---

## 1. Data inventory (evidence)

Stored OHLCV data per symbol, queried directly from the dev database:

```sql
-- via Django ORM: Candle.objects.values('instrument_id','timeframe')
--   .annotate(n=Count('id'), first=Min('timestamp'), last=Max('timestamp'))
```

| instrument_id | timeframe | rows | first | last |
|---|---|---|---|---|
| 12345 (NSE:RELIANCE) | 1D | 5 | 2026-08-14 | 2026-08-18 |
| 67890 (NSE:INFY) | 1D | 5 | 2026-08-14 | 2026-08-18 |

Raw output (both `tradevision_db` and `tradevision_test`):

```
total candles: 10
per instrument/tf: [{'instrument_id': 12345, 'timeframe': '1D', 'n': 5},
                    {'instrument_id': 67890, 'timeframe': '1D', 'n': 5}]
earliest: 2026-08-14 00:00:00+00:00   latest: 2026-08-18 00:00:00+00:00
```

Ten candles, five days, one timeframe. This is **no data**, not "insufficient
data": no statistical statement of any kind can be derived from it. It is the
synthetic `paper`-provider output persisted by the readiness batch's
`backfill_historical` dry-run/real-run checks.

**No Sharpe, drawdown, win rate, or any performance metric is computed or
reported against this dataset anywhere in this document.**

## 2. Credential status (evidence)

Checked the resolved Django settings (which read `backend/.env`):

```
ZERODHA_API_KEY      = ''
ZERODHA_ACCESS_TOKEN = ''
ZERODHA_API_SECRET   = ''
MARKET_DATA_PROVIDER = 'mock'
BROKER_ADAPTER       = 'paper'
```

No Kite Connect credentials are configured (they are also absent from
`.env`). The Zerodha provider (`apps/market_data/infrastructure/providers/
zerodha_provider.py`) authenticates to `api.kite.trade` with
`Authorization: token {api_key}:{access_token}` — with both empty it cannot
fetch anything. Note the Kite historical data API is itself a **paid
subscription** (developer API access + historical data add-on), separate from a
trading account; see §6.

## 3. No historical backfill has ever run (evidence)

- `BacktestRun.objects.count() == 0` — no backtest has ever been executed.
- `Candle` has no provenance/source field, but all 10 rows' OHLCV match the
  synthetic `paper` provider's seeded output from the readiness batch, and the
  Redis circuit-breaker keys for `historical-sync` are absent.
- The only `historical_sync_service.backfill` invocations ever were the
  readiness batch's **`paper`**-provider dry-run and real-run smoke checks
  (which produced these 10 candles). No Zerodha backfill has ever run.
- There is no sync-run audit model, so there is no run history to query — the
  absence of candles, credentials, and runs is the evidence.

## 4. Per rule × regime — verdict

All registered rules (the 8 builtin rules: `price_movement_v1`,
`volume_spike_v1`, `breakout_v1`, `long_momentum_v1`, `short_sell_v1`,
`volatility_breakout_v1`, `high_beta_breakout_v1`, `short_breakdown_v1`) × all
regimes (`BULLISH`, `BEARISH`, `RANGING`, `VOLATILE`, `BREAKOUT`, `BREAKDOWN`):

**INSUFFICIENT-DATA** for every (rule, regime) pair.

`RuleConfig.validated_regimes` is **untouched** (no writes of any kind). No rule
is marked `GO` or `NO-GO`. The ADR-029 §4 gate remains closed for every rule,
which is correct: the gate exists to block undervalidated rules, and it is
doing its job.

## 5. Significance-testing machinery — built and ground-truth tested

### 5.1 What was built

`backend/apps/backtesting/domain/significance.py` — a pure module implementing
the randomized-entry baseline comparison:

- Input: a rule's realized per-trade net P&L sequence (costs already applied).
- Method: **sign-flip permutation test at matching trade frequency** — the trade
  count and the multiset of realized outcome magnitudes are preserved, and each
  trade's sign is randomized (`n_shuffles` times, default 1000), destroying any
  signal-consistent entry timing. The test statistic is mean per-trade net P&L.
- Output: `SignificanceResult` with observed mean, baseline mean/std, z-score,
  one-sided `p_value` (`(1 + count(null_mean ≥ observed_mean)) / (1 + n_shuffles)`),
  and `verdict` ∈ `SIGNIFICANT` / `NOT_SIGNIFICANT` / `None`.
- Honesty guard: below `min_trades` (default 10) the test is **not attempted** —
  `verdict=None`, `reason="INSUFFICIENT_TRADES"`. No edge evidence is neither
  evidence of edge nor of no edge.
- Deterministic: `seed` parameter for reproducible results.

### 5.2 Ground-truth tests (tested against known answers, not TradeVision rules)

`backend/apps/backtesting/tests/test_significance.py` — 9 tests, all passing:

| Fixture | Expected | Result |
|---|---|---|
| Literally random (symmetric zero-mean) trade P&L | `NOT_SIGNIFICANT` | PASS |
| Injected obvious positive edge (uniformly winning trades) | `SIGNIFICANT` | PASS |
| Sample below `min_trades` | `verdict=None` (`INSUFFICIENT_TRADES`) | PASS |
| Empty sequence | `verdict=None` | PASS |
| Exact `min_trades` boundary honored | `None` below, `SIGNIFICANT` at/above | PASS |
| Same `seed` ⇒ identical result | reproducible | PASS |
| Decimal input accepted | behaves like float | PASS |
| Invalid `n_shuffles`/`alpha` rejected | `ValueError` | PASS |
| Baseline preserves trade frequency and has variance | count fixed, `std>0` | PASS |

## 6. Synthetic pipeline smoke test — LABELED, NOT EDGE EVIDENCE

⚠️ SYNTHETIC SMOKE TEST — NOT EDGE EVIDENCE — 10 candles, not a
statistically meaningful sample. This section exists only to confirm the
pipeline runs; treat every number below as meaningless.

`backend/apps/backtesting/tests/test_edge_validation_smoke.py` replays TA
snapshots built from the OHLCV of the 10 stored synthetic candles (the
production candle→TA handoff) through the real event chain, then drives the
orchestrators:

| Pipeline component | Executes without error | Schema well-formed |
|---|---|---|
| `EdgeValidationService.evaluate` (single-run + walk-forward) | PASS | PASS |
| `WalkForwardService.execute` direct | PASS | PASS |
| `CostSensitivityService.execute` (cost grid) | PASS | PASS |
| Significance wiring: fills → per-rule net trade P&L → `shuffled_baseline_significance` | PASS | PASS |

4/4 smoke tests pass. No performance value is asserted by these tests and no
performance value from this run is reproduced here. Nothing in this module
reads or writes `RuleConfig.validated_regimes`.

Full backtesting suite: **166 passed** (includes the new significance + smoke
tests; no regressions).

## 7. What is needed to actually run this batch for real

1. **Real historical data source** — the decision from §2/§3 above. Two paths:
   - **Zerodha Kite Connect** (`ZERODHA_API_KEY` + `ZERODHA_ACCESS_TOKEN`):
     requires the paid developer-API + historical-data subscription, an
     out-of-band `request_token → generate_session` login exchange, and is
     rate-limited. This is the provider the codebase already implements, so the
     `manage.py backfill_historical` CLI is ready to use it unchanged.
   - **Data vendor export**: a CSV/pandas dump of years of daily data for the
     NIFTY 50 / a symbol universe, imported into `Candle` (a small loader would
     be needed — none exists today).
2. **Backfill years, not weeks**: daily bars for the instrument universe over a
   multi-year window (respecting Kite's historical data depth caps), so each
   rule can accumulate a statistically meaningful trade count.
3. **Then re-run this batch**: `WalkForwardService` + `CostSensitivityService`
   at realistic Indian equity costs (STT + brokerage + slippage folded into the
   engine's `commission_rate`/`slippage_bps`), per-rule/per-regime, feeding
   per-trade net P&L into `shuffled_baseline_significance`, and only then
   considering `RuleValidationService.validate_run` to write `validated_regimes`.
   Estimated backfill duration depends on the Kite rate limit (Kite historical
   is throttled per-connection; expect minutes-to-hours for a full universe ×
   years, and budget quota headroom for retries).

## 8. Overall verdict

**NO EDGE VERDICT POSSIBLE — prerequisite unmet.**

The current rule set, as it stands, has no *demonstrable* edge — because it
has never been measured against real data. Nothing in this report implies an
edge exists; nothing implies it doesn't. No rule is GO; no rule is NO-GO;
every (rule, regime) pair is INSUFFICIENT-DATA, and `validated_regimes` is
unchanged. That is the correct and complete result of this batch as executed.
