"""PIPELINE-HEALTH-1 — domain exceptions."""


class PipelineHealthError(Exception):
    """Base class for pipeline-health domain errors."""


class UnsupportedEventTypeError(PipelineHealthError):
    """Raised when an event has no mapping to a pipeline stage.

    Defensive: consumers only subscribe to known event types, so this is
    only reachable via a misconfigured subscription or a logic bug.
    """

    def __init__(self, event_type: str) -> None:
        self.event_type = event_type
        super().__init__(f"Unsupported pipeline-health event type: {event_type}")


class MissingSymbolError(PipelineHealthError):
    """Raised when a per-symbol event lacks a resolvable symbol scope.

    The consumer treats this as a transient, logged-and-skipped condition
    (never raising out of the handler boundary), so a bad payload can never
    take down the pipeline or corrupt heartbeat state.
    """

    def __init__(self, event_type: str, event_id: str) -> None:
        self.event_type = event_type
        self.event_id = event_id
        super().__init__(
            f"Event {event_id} of type {event_type} has no resolvable symbol"
        )
