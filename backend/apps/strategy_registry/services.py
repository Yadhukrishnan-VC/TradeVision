from __future__ import annotations

import logging

from apps.strategy_registry.models import (
    StrategySymbolAffinity,
    TradingStrategy,
    TradingStrategyStatus,
)
from core.execution_context import get_forced_strategy_id

logger = logging.getLogger(__name__)


class StrategyMatcher:
    """Pick the strategy for a symbol's live packet.

    Order of preference (per user decision — per-stock backtest evidence):

    1. A strategy pinned by the current backtest-run context
       (``bind_forced_strategy``); strategy-isolated replay always selects the
       run's own strategy so fills/metrics stay attributable.
    2. Evidence-backed ranking for this symbol: strategies with a
       ``StrategySymbolAffinity`` row for ``symbol`` first, ranked by
       ``rank`` (1 = best backtested on that stock).
    3. Fallback to the strategy's global ``priority`` (default strategies).

    ``symbol_filter`` / ``sector_filter`` still gate candidates in every path.
    """

    def match(self, packet: object) -> TradingStrategy | None:
        symbol = getattr(packet, "symbol", None)

        forced_id = get_forced_strategy_id()
        if forced_id is not None:
            forced = TradingStrategy.objects.filter(
                id=forced_id,
                status=TradingStrategyStatus.ACTIVE,
                is_deleted=False,
            ).first()
            if forced:
                if self._passes_filters(forced, packet, symbol):
                    logger.info(
                        "strategy_matched_forced",
                        extra={
                            "strategy_id": str(forced.id),
                            "strategy_name": forced.name,
                            "symbol": symbol,
                        },
                    )
                    return forced
            logger.info(
                "strategy_forced_unavailable",
                extra={"strategy_id": str(forced_id), "symbol": symbol},
            )

        candidates = list(
            TradingStrategy.objects.filter(
                status=TradingStrategyStatus.ACTIVE,
                is_deleted=False,
            )
        )

        affinity_rank: dict[str, int] = {}
        if symbol:
            for row in StrategySymbolAffinity.objects.filter(symbol=symbol).only(
                "strategy_id", "rank"
            ):
                affinity_rank[str(row.strategy_id)] = row.rank

        candidates.sort(
            key=lambda s: (
                0 if str(s.id) in affinity_rank else 1,
                affinity_rank.get(str(s.id), 10_000),
                s.priority,
                s.created_at.isoformat() if s.created_at else "",
            )
        )

        for strategy in candidates:
            if not self._passes_filters(strategy, packet, symbol):
                continue
            ranked = affinity_rank.get(str(strategy.id))
            logger.info(
                "strategy_matched",
                extra={
                    "strategy_id": str(strategy.id),
                    "strategy_name": strategy.name,
                    "symbol": symbol,
                    "symbol_rank": ranked,
                },
            )
            return strategy

        logger.info(
            "no_strategy_matched",
            extra={"symbol": symbol},
        )
        return None

    @staticmethod
    def _passes_filters(strategy: TradingStrategy, packet: object, symbol: str | None) -> bool:
        if strategy.symbol_filter and strategy.symbol_filter != symbol:
            return False
        if strategy.sector_filter:
            sector = getattr(packet, "sector", None)
            if sector and strategy.sector_filter != sector:
                return False
        return True