from __future__ import annotations

import logging

from apps.strategy_registry.models import TradingStrategy, TradingStrategyStatus

logger = logging.getLogger(__name__)


class StrategyMatcher:
    def match(self, packet: object) -> TradingStrategy | None:
        symbol = getattr(packet, "symbol", None)
        if not symbol:
            return None

        strategies = TradingStrategy.objects.filter(
            status=TradingStrategyStatus.ACTIVE,
        ).order_by("priority", "created_at")

        for strategy in strategies:
            if strategy.symbol_filter and strategy.symbol_filter != symbol:
                continue
            if strategy.sector_filter:
                sector = getattr(packet, "sector", None)
                if sector and strategy.sector_filter != sector:
                    continue
            logger.info(
                "strategy_matched",
                extra={
                    "strategy_id": str(strategy.id),
                    "strategy_name": strategy.name,
                    "symbol": symbol,
                },
            )
            return strategy

        logger.info(
            "no_strategy_matched",
            extra={"symbol": symbol},
        )
        return None
