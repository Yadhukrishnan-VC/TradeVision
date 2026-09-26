from __future__ import annotations

from django.db import models

from core.constants import AIProviderName
from core.models import BaseModel


class TradingStrategyStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    INACTIVE = "INACTIVE", "Inactive"
    RETIRED = "RETIRED", "Retired"


class TradingStrategy(BaseModel):
    name = models.CharField(max_length=128, unique=True)
    status = models.CharField(
        max_length=16,
        choices=TradingStrategyStatus.choices,
        default=TradingStrategyStatus.INACTIVE,
        db_index=True,
    )
    priority = models.IntegerField(default=0, db_index=True)
    symbol_filter = models.CharField(max_length=20, null=True, blank=True)
    sector_filter = models.CharField(max_length=64, null=True, blank=True)
    preferred_provider = models.CharField(
        max_length=32,
        null=True,
        blank=True,
        choices=[(p.value, p.name) for p in AIProviderName],
    )
    confidence_threshold = models.DecimalField(max_digits=5, decimal_places=4, default=0.6000)
    risk_threshold = models.DecimalField(max_digits=5, decimal_places=4, default=0.5000)

    class Meta:
        ordering = ["priority", "created_at"]
        verbose_name = "Trading Strategy"
        verbose_name_plural = "Trading Strategies"

    def __str__(self) -> str:
        return f"TradingStrategy({self.name}, status={self.status})"


class StrategySymbolAffinity(BaseModel):
    """Per-symbol strategy performance ranking (evidence-backed).

    One row per (strategy, symbol) that cleared the ADR-029-style gate on a
    completed backtest for that symbol. ``rank`` orders strategies for a
    symbol from best to worst; ``StrategyMatcher`` prefers ``rank == 1`` when
    it picks a strategy for live packets of that symbol, falling back to
    global ``priority`` when no evidence exists.

    ``score`` is a documented, deterministic composite of the source run's
    metrics (see ``SymbolRankingService``); ``source_run`` keeps full
    provenance so nobody can claim rank 1 without a real backtest behind it.
    """

    strategy = models.ForeignKey(
        TradingStrategy,
        on_delete=models.CASCADE,
        related_name="symbol_affinities",
    )
    symbol = models.CharField(max_length=100, db_index=True)
    rank = models.PositiveIntegerField(default=1, help_text="1 = best-performing strategy for this symbol")
    score = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    expectancy = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    profit_factor = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    sharpe_ratio = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    max_drawdown_pct = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    trade_count = models.IntegerField(default=0)
    source_run = models.ForeignKey(
        "backtesting.BacktestRun",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Completed backtest run the ranking was computed from.",
    )
    evaluated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["symbol", "rank"]
        constraints = [
            models.UniqueConstraint(
                fields=["strategy", "symbol"],
                name="uniq_strategy_symbol_affinity",
            )
        ]
        indexes = [
            models.Index(fields=["symbol", "rank"], name="idx_strategy_symbol_affinity"),
        ]
        verbose_name = "Strategy-Symbol Affinity"
        verbose_name_plural = "Strategy-Symbol Affinities"

    def __str__(self) -> str:
        return f"StrategySymbolAffinity({self.symbol} #{self.rank} {self.strategy.name})"
