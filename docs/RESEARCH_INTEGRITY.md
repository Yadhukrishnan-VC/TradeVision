# Research Integrity Suite — Batch 2

Adversarial test suite proving the backtesting pipeline does not leak future
information, does not execute on the same candle it "saw" close, does not
contaminate its in-sample/out-of-sample split, and does not introduce
survivorship bias.

Suite location: `backend/tests/research_integrity/` (17 tests, all through the
REAL event chain where possible — `TechnicalAnalysisIngestionService` → EventBus
→ intelligence → rule_engine → risk_management → execution → PaperBroker).

Run:

```bash
cd backend
POSTGRES_DB=tradevision_db POSTGRES_USER=tradevision \
POSTGRES_PASSWORD=tradevision_password POSTGRES_HOST=localhost \
POSTGRES_PORT=5432 REDIS_URL=redis://localhost:6379/0 \
EVENT_BUS_IMPLEMENTATION=fake .venv/bin/pytest tests/research_integrity -q
```

Suite is part of the default test discovery (`testpaths` includes `tests/`).

---

## Attacks attempted and outcomes

| # | Attack | Where probed | Outcome |
|---|--------|--------------|---------|
| 1 | IS/OOS split keyed on wall-clock `order.created_at` (2026) instead of simulated bar time (2024) → every real-replay trade lands in OOS, IS always empty | `BacktestStatsService.run_stats` | **PROVEN DEFECT — FIXED** (RESEARCH-INTEGRITY-1) |
| 2 | Bar with no `open` field → runner falls back to that bar's `close` to fill a deferred order (price not yet known at the open) | `BacktestRunnerService` bar-open fill | **PROVEN DEFECT — FIXED** (RESEARCH-INTEGRITY-2) |
| 3 | Order generated on bar N executes on bar N itself (same candle as the signal) | full replay | No defect: fills are deferred to the next bar's open |
| 4 | Bars after `range_end` (or 1 min before `range_start`) leak into the sample | `find_in_range` | No defect: window is inclusive on both ends, everything outside is excluded |
| 5 | Walk-forward windows share state → one window's trades bleed into the next | `WalkForwardService` + `run_stats` | No defect: dedicated funded account per window; stats strictly account-scoped |
| 6 | Fill/execution timestamps leak wall-clock time | `Fill.occurred_at` | No defect: fills carry simulated bar time, always within the declared range |
| 7 | Historical bars of delisted/unlisted symbols are silently dropped (survivorship-biased universe) | `BacktestRunnerService` snapshot fetch | No defect: single-symbol explicit backtest, no listing/universe filter — every in-range bar is processed |

Two of the seven attacks surfaced real defects that are now fixed and
regression-pinned. The remaining five are no-defect findings pinned as tests so
future regressions fail loudly.

---

## Findings

### RESEARCH-INTEGRITY-1 — IS/OOS partition used wall-clock time (PROVEN, FIXED)

`run_stats` partitioned trades using `order.created_at`. That field is
`auto_now_add` — the wall-clock time the order was written (2026 for a replay
run in the present). Backtest bars are historical (2024). The IS/OOS split
therefore compared 2026 against a 2024 `split_ts`, so **every trade fell into
OOS and the in-sample half was always empty** — a silent, systemic
contamination of the research split.

Proof (before fix): 3-bar replay → `trade_count=2`, `in_sample=0`,
`out_of_sample=2`, IS empty.

Fix in `backend/apps/backtesting/services.py:279-283,429`:
`run_stats` now builds a `first_fill_at` map from the run's fills (the
simulated `Fill.occurred_at`, earliest per order) and partitions on
`first_fill_at[order_id] or order.created_at`. A trade's split time is the time
its first fill executed **in simulated market time**.

Boundary semantics: `occurred_at <= split_ts` → in-sample (inclusive); one
second after → out-of-sample. Pinned by
`test_is_oos_contamination.py::test_fill_exactly_on_split_is_in_sample_and_one_second_after_is_oos`.

Regression proof: reverting the fix makes
`test_real_replay_partitions_by_simulated_fill_time` fail (both trades → OOS).

### RESEARCH-INTEGRITY-2 — look-ahead fill on a bar with no open (PROVEN, FIXED)

The runner computed the next bar's execution price with
`raw.get("open") or raw.get("close")`. If a bar arrived without an `open`, a
deferred order was silently filled at that bar's **close** — a price only
known at the end of the very bar being executed at its open. That is look-ahead
bias: the simulated execution "knew" the close before the open existed.

Fix in `backend/apps/backtesting/services.py:104`:
`bar_open = self._extract_decimal(raw.get("open"))` — a bar without an `open`
is skipped for bar-open fills (the order stays pending) and the fill only
happens at a later bar that has an `open`. Fail-safe: the run still completes;
nothing crashes; no order is ever priced at a not-yet-known close.

Pinned by `test_lookahead_bias.py`:
- `test_missing_open_skips_fill_never_falls_back_to_close` — order generated on
  the signal bar is filled at the next bar that HAS an open (112), never the
  no-open bar's close (107).
- `test_no_open_bar_is_fail_safe_never_crashes` — run completes, all surviving
  orders filled at valid opens.

Regression proof: reverting the fix makes both tests fail (fill price becomes
the no-open bar's close).

### RESEARCH-INTEGRITY-3 — no same-candle execution (no defect)

Every order generated on bar N is filled at bar N+1's open (price and simulated
timestamp verified). No order is ever filled on the bar whose indicators
generated it. Pinned by `test_same_candle_execution.py` and
`test_timestamp_leakage.py::test_fill_never_predates_the_executing_bar`.

### RESEARCH-INTEGRITY-4 — no future-data leakage (no defect)

`find_in_range` is inclusive on both ends: bars exactly at `range_start` and
`range_end` are processed, and bars one minute outside either bound are
excluded (`test_future_leakage.py`). A future bar after `range_end` with an
extreme signal produces zero orders and zero bars processed.

### RESEARCH-INTEGRITY-5 — walk-forward contamination impossible (no defect)

`WalkForwardService` creates a dedicated funded `Account` per window, and
`run_stats` queries strictly by `account_id`. A contaminating trade injected
into window 0's account never appears in windows 1–3
(`test_walk_forward_contamination.py`); the direct invariant
(account A's trade invisible to account B's `run_stats`) also holds.

### RESEARCH-INTEGRITY-6 — fill timestamps are simulated time (no defect)

All `Fill.occurred_at` values sit inside `[range_start, range_end]`, year 2024,
never wall-clock 2026 (`test_timestamp_leakage.py`). Bars with duplicate
timestamps are all processed independently (no unique constraint, no collision).

### RESEARCH-INTEGRITY-7 — no survivorship bias in the engine (no defect)

The backtest is single-symbol and explicit: the caller names the symbol and
`find_in_range` returns every in-range snapshot for it with no
listing/liquidity/universe filter (`test_survivorship_bias.py`). All in-range
bars are processed regardless of current listing state. Survivorship risk in a
research process would come from hand-selecting survived symbols upstream — a
data-selection concern the engine cannot and does not mask.

### RESEARCH-INTEGRITY-8 — market-hours gating is real (observed)

Bars timestamped outside NSE market hours (e.g. 00:00 UTC = 05:30 IST) are
processed but produce no order: the risk layer's market-hours gate rejects
them. Research datasets must place bars within trading hours for the pipeline
to act on them. Not a defect; documented so future adversarial datasets
timetamp bars at 07:00 UTC (12:30 IST) or later.

---

## Remaining risks

1. **Final-bar flush fills at the last bar's close.** An order generated on the
   last bar of a replay is flushed at that bar's close (same-candle execution
   on the boundary bar). This is a deliberate end-of-sample liquidation
   convention pinned by
   `test_same_candle_execution.py::test_final_bar_flush_is_documented_end_of_sample_convention`.
   It is a real look-ahead on the last bar and is kept ONLY because changing it
   would alter the parallel team's pinned behaviour. A strategy that relies on
   it sees an artificial same-close exit; safest interpretation is to treat the
   final close fill as sample-end liquidation. **Recommend** revisiting after
   Batch 1/2 converge.

2. **`price_source` wall-clock/sim-time mismatch.** During replay, a
   wall-clock-dated session fact (2026-08-19 09:15 IST opening candle) reaches
   `MarketDataService.get_quote`, which builds a `MarketDataRequest` with
   `from > to` and raises `ValueError: from_timestamp must be strictly before
   to_timestamp`. It is logged as `ERROR portfolio_price_lookup_failed` and
   swallowed — the run completes and research outputs are unaffected, but the
   error log is noisy and the price source call is effectively dead during
   replay. Contained, not fixed; revisit in a Batch focused on the
   portfolio/market-data time handling.

3. **Position sizing exposure cap.** The risk layer caps per-account exposure
   at 1,000,000 regardless of deposited capital, so at most two ~350k
   `long_momentum` orders fit per run; the third signal is rejected with
   `MAX_EXPOSURE_EXCEEDED`. The adversarial tests exploit this determinism
   deliberately. If the cap is ever intended to scale with equity, the pinned
   order counts here will change.

4. **Test-DB hygiene (pre-existing).** The watchlist test's `transaction=True`
   pattern and the replay test's stored events leak rows between suites; the
   research suite itself is self-contained (fresh accounts per run, patched
   calendar via `monkeypatch`) and does not add to the leaks.

5. **Replayed `order.created_at` is wall clock.** Remains wall-clock by design
   (it is an audit timestamp). It no longer drives any research statistic;
   anything that could read it as market time is a future risk and should
   prefer `Fill.occurred_at`.

---

## Coverage map

| File | Attack covered | Tests |
|------|----------------|-------|
| `test_same_candle_execution.py` | same-candle execution (3) | 3 |
| `test_lookahead_bias.py` | open→close fallback (2) | 2 |
| `test_future_leakage.py` | out-of-range data (4) | 2 |
| `test_is_oos_contamination.py` | IS/OOS wall-clock split, boundary, exact-once (1) | 3 |
| `test_walk_forward_contamination.py` | cross-window bleed (5) | 2 |
| `test_timestamp_leakage.py` | wall-clock fill timestamps, duplicate bars (6) | 3 |
| `test_survivorship_bias.py` | universe/listing filters (7) | 2 |

Defects found: 2 (both fixed and regression-pinned).
No-defect findings pinned: 5. Remaining risks documented: 5.
