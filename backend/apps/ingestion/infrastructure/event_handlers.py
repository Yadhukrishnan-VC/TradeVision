from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ``ingestion`` is a publisher-only app in Batch 1.
# No event handlers are registered here. The handlers that consume
# ``ingestion.RawAlertReceived`` and ``ingestion.ScanResultReceived``
# will be implemented by Batch 2 (signals_engine).


def register_handlers(event_bus: Any = None) -> None:
    """Register ingestion event handlers on the event bus.

    Placeholder for future subscriptions. Currently a no-op.
    """
    logger.debug("ingestion_event_handlers_registered_noop")
