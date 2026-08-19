# Edge Validation Report V2 — TradeVision

**Generated:** 2026-08-19T17:49:35.390219+00:00

**Symbols analyzed:** 3 (RELIANCE, TCS, INFY)
**Timeframe:** 1D
**Years of history:** 3
**Walk-forward window:** 252 days
**Walk-forward step:** 63 days
**In-sample ratio:** 0.70
**Realistic commission rate:** 0.0013 (0.13%)
**Realistic slippage:** 5.0 bps
**Significance test:** shuffled baseline, n_shuffles=1000, alpha=0.05, min_trades=10

---

## Overall Verdicts

| Rule ID | Regime | Verdict | Symbols | Total Trades | Significance |
|---------|--------|---------|---------|--------------|--------------|

---

## Per-Symbol Detail

---

## Notes

- **GO**: Rule has positive expectancy, profit factor > 1, and statistically significant edge at realistic costs.
- **NO-GO**: Rule fails the edge criterion at realistic costs.
- **INSUFFICIENT-DATA**: Not enough trades to make a determination (less than min_trades).
- Significance test uses shuffled baseline (sign-flip permutation) at matching trade frequency.
- Regime detection is currently a placeholder (UNKNOWN) — requires PatternEngine integration.
- This report does NOT write to RuleConfig.validated_regimes. That step requires human review.
