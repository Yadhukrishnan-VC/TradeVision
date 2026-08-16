# 06 — Charts and Visualization

Data for charts comes exclusively from verified backend fields. All money/ratio values arrive as **strings**.

## Chart inventory (what each chart plots, and the exact source fields)

1. **Equity curve** — from `stats.equity_at_completion` is a scalar; the per-trade path is derivable from `stats.trades[].net_pnl` (cumulative) or the bucket `equity_curve` arrays:
   - `stats.in_sample.equity_curve` / `stats.out_of_sample.equity_curve` (arrays of Decimal-as-string; first element = initial equity).
   - NOTE: `in_sample`/`out_of_sample` bucket objects in `run_stats` DO contain `equity_curve` and `returns` arrays (verified in `services.py:282-303`). Use these for IS/OOS equity curves.
   - ⚠ The top-level `stats` dict does NOT return a single merged `equity_curve` array key (only `equity_at_completion`). Build the merged path from `trades[].net_pnl` cumulative sum, or plot the two IS/OOS curves directly.
2. **Daily returns** — `stats.in_sample.returns` / `stats.out_of_sample.returns` arrays (Decimal ratios). Histogram for return distribution; ⚠ per-day grouping not exposed — use the arrays as-is.
3. **Drawdown** — `stats.max_drawdown_pct` (scalar) is a summary; a drawdown **series** is NOT returned by `run_stats` (only max). Render max drawdown as a stat card, not a chart. ⚠ DO NOT fabricate a drawdown curve.
4. **Regime breakdown** — `stats.by_regime`: for each regime, a bucket with `win_rate`, `expectancy`, `profit_factor`, `net_pnl`, `trade_count`, `equity_curve`. Bar chart of `expectancy` or `net_pnl` per regime; chips for regime names.
5. **Per-rule attribution** — `stats.by_rule`: same bucket fields per `rule_id`. Horizontal bar chart of `expectancy` / `profit_factor` per rule; `unattributed_trade_count` shown as an "unattributed" bar.
6. **Walk-forward OOS distribution** — `walk-forward` response `distribution.out_of_sample_*` gives `{count, min, max, median, count_positive}`. Render as stat cards (min/max/median) + a small "windows positive / total" meter. The raw per-window series (`windows[]`) can plot OOS expectancy per window index (line/bar).
7. **Edge validation** — `by_rule[].baseline_has_edge` vs `realistic_cost_has_edge` (+ `flipped`). Render a rule x cost-level matrix / heatmap-like grid (baseline vs realistic), never a fabricated line chart.
8. **Cost sensitivity** — `by_rule[].series[]` of `{cost_level, expectancy}` — this IS a plot-ready series: expectancy vs cost_level line per rule, with `breakeven_commission_rate` marked. Classification badge (BREAKEVEN_FOUND / NEVER_PROFITABLE / SURVIVES_FULL_RANGE).
9. **PnL analytics / daily rollup / performance** — ⚠ bodies not fully verified; render whatever keys arrive (defensive). If `daily` rollup returns date+pnl pairs, plot an area/bar chart; otherwise show cards.
10. **Portfolio composition** — `total_market_value`, `total_cost_basis`, `cash_balance` + holdings with `allocation_pct` — donut chart of holdings allocation (percentages), stat cards for totals.

## Chart library guidance

No chart library is installed. The fixed stack allows adding one (e.g. `recharts` or lightweight `@visx`), or render simple SVG. Keep it dependency-light. For equity curves use area+line; for distributions use bars; for the cost-sensitivity series use line charts.

## Rules

- **Never fabricate series.** If a chart's series doesn't exist in the payload (e.g. drawdown curve, intraday PnL), do NOT generate it — render the summary stat or a "no data" empty state.
- **Decimal formatting**: values arrive as strings; format INR (₹) with 2 decimals and % with 2 decimals, suffix-free for ratios like Sharpe (2 decimals, no %).
- `null` ratio fields (e.g. `profit_factor: null` when a bucket is empty) render as `--`, never `0`.
- Use consistent color encoding: profit green / loss red; GO green, NO_GO red, INSUFFICIENT_DATA amber (ADR-029 gate); regime chips pastel palette.