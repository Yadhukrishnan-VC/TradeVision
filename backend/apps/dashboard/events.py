from __future__ import annotations

"""Dashboard-published event definitions.

Dashboard publishes internal domain events via ``projection/internal_events.py``.
These events are visible only within the dashboard bounded context and are never
published to the shared EventBus. This module exists as a declaration point for
dashboard-scoped event types so that other modules can reference them without
importing from the projection layer.
"""

EVENT_POSITION_SNAPSHOT_PROJECTED = "position_snapshot_projected"
EVENT_ORDER_STATUS_PROJECTED = "order_status_projected"
EVENT_TRADE_RECORD_PROJECTED = "trade_record_projected"
