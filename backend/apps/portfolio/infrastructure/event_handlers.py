"""Batch M3.6 — portfolio event handlers.

Purely additive registration for the stop-loss exit evaluation against
``technical_analysis.TechnicalAnalysisCompleted`` events. Follows the
``register_handlers(event_bus)`` convention every other app uses; picked up
automatically by ``EventBusService.register_all_handlers()`` auto-discovery.
"""

from __future__ import annotations

import logging
from typing import Any

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.portfolio.application.exit_evaluation_service import ExitEvaluationService

logger = logging.getLogger(__name__)


def handle_ta_completed(event: DomainEvent) -> None:
    """Evaluate the bar against the account's open position's stop-loss.

    Never raises for routine conditions (see ``ExitEvaluationService``);
    a failed exit evaluation is logged, not surfaced as a handler failure
    (production stays safe regardless of this new subscriber's behaviour).
    """
    try:
        ExitEvaluationService().evaluate_ta_completed(event)
    except Exception as exc:  # pragma: no cover - defensive boundary
        logger.exception(
            "exit_evaluation_failed",
            extra={
                "event_id": str(event.event_id),
                "symbol": event.payload.get("symbol", ""),
                "error": str(exc),
            },
        )


def register_handlers(event_bus: Any = None) -> None:
    bus = event_bus or get_event_bus()
    bus.subscribe(
        "technical_analysis.TechnicalAnalysisCompleted",
        handle_ta_completed,
        consumer_group="portfolio",
    )
    logger.debug("portfolio_handlers_registered")