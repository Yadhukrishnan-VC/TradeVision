from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def register_handlers(event_bus: Any = None) -> None:
    """Register technical analysis event handlers on the event bus.

    Currently ``technical_analysis`` is a publisher-only app.
    It publishes ``technical_analysis.TechnicalAnalysisCompleted``
    events.  Consumers will subscribe in downstream apps.
    """
    logger.debug("technical_analysis_event_handlers_registered_noop")
