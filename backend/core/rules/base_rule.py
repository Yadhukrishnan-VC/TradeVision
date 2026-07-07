"""
TradeVision AI — Abstract rule base class.

Every rule in the rule engine implements this interface. Rules are stateless,
independently unit-testable value objects that accept an IntelligencePacket
and either fire (returning a RuleResult) or pass (returning None).

Design constraints:
  - Rules must never raise exceptions. All errors are caught internally and
    logged; the return value is None (no-fire) on error.
  - Rules must never perform I/O (no database or network calls). They operate
    exclusively on the data already assembled in the IntelligencePacket.
  - Rules are registered in RuleRegistry (core/rules/rule_registry.py, Batch 3).
"""

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import final

from core.events.event_types import AnalysisEvent, EventType, IntelligencePacket
from core.utils import get_now, generate_uuid

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Supporting types
# ---------------------------------------------------------------------------


class RuleSeverity(str, Enum):
    """
    Relative importance of events produced by a rule.

    Severity influences notification priority and AI prompt template selection.
    """

    LOW = "LOW"
    """Minor signal — informational, no immediate action implied."""

    MEDIUM = "MEDIUM"
    """Notable signal — worth monitoring; may develop into a HIGH event."""

    HIGH = "HIGH"
    """Significant event — requires timely AI analysis and user notification."""

    CRITICAL = "CRITICAL"
    """Urgent event — circuit breaker, earnings miss, major news; alert immediately."""


@dataclass(frozen=True)
class RuleResult:
    """
    The output of a rule evaluation when the rule fires.

    A RuleResult is converted into an AnalysisEvent by the RuleRegistry
    and then dispatched to the AI Orchestrator via the EventBus.

    Attributes:
        rule_id:       Identifier of the rule that produced this result.
        event_type:    EventType classification for downstream routing.
        severity:      Severity level for prioritisation.
        trigger_data:  Structured dict explaining why the rule fired.
                       Must be JSON-serialisable (Decimal values as str).
        description:   Human-readable one-line summary for logging.
    """

    rule_id: str
    event_type: EventType
    severity: RuleSeverity
    trigger_data: dict = field(default_factory=dict)
    description: str = ""

    def to_analysis_event(
        self,
        symbol: str,
        packet: IntelligencePacket,
        *,
        timestamp: datetime | None = None,
    ) -> AnalysisEvent:
        """
        Convert this RuleResult into an AnalysisEvent.

        Args:
            symbol:    The stock symbol that triggered the rule.
            packet:    The IntelligencePacket at the time of firing.
            timestamp: Event timestamp. Defaults to ``get_now()`` (UTC).

        Returns:
            A fully populated, immutable AnalysisEvent.
        """
        return AnalysisEvent(
            id=generate_uuid(),
            event_type=self.event_type,
            symbol=symbol,
            timestamp=timestamp or get_now(),
            rule_id=self.rule_id,
            trigger_data=self.trigger_data,
            intelligence_packet=packet,
        )


# ---------------------------------------------------------------------------
# Abstract base rule
# ---------------------------------------------------------------------------


class BaseRule(ABC):
    """
    Abstract interface for all market monitoring rules.

    Subclasses implement ``evaluate()`` and declare their metadata via
    abstract properties. The rule engine calls ``safe_evaluate()`` rather
    than ``evaluate()`` directly to guarantee that exceptions are never
    propagated upward.

    Example implementation::

        class PriceMovementRule(BaseRule):

            @property
            def rule_id(self) -> str:
                return "price_movement_v1"

            @property
            def name(self) -> str:
                return "Price Movement Rule"

            @property
            def event_type(self) -> EventType:
                return EventType.PRICE_MOVEMENT

            @property
            def severity(self) -> RuleSeverity:
                return RuleSeverity.HIGH

            def evaluate(self, packet: IntelligencePacket) -> RuleResult | None:
                threshold = Decimal("2.0")
                change = abs(packet.price_context.change_pct)
                if change >= threshold:
                    return RuleResult(
                        rule_id=self.rule_id,
                        event_type=self.event_type,
                        severity=self.severity,
                        trigger_data={
                            "change_pct": str(packet.price_context.change_pct),
                            "threshold_pct": str(threshold),
                        },
                        description=f"{packet.price_context.change_pct:+.2f}% price movement",
                    )
                return None
    """

    # ------------------------------------------------------------------
    # Abstract metadata — must be implemented by every concrete rule
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def rule_id(self) -> str:
        """
        Unique, stable identifier for this rule.

        Used in logging, audit trails, and RuleExecution records. Follow
        the convention ``snake_case_v{version}`` (e.g. ``price_movement_v1``).
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable display name shown in dashboards and logs."""

    @property
    @abstractmethod
    def event_type(self) -> EventType:
        """The EventType this rule produces when it fires."""

    @property
    @abstractmethod
    def severity(self) -> RuleSeverity:
        """Default severity of events produced by this rule."""

    # ------------------------------------------------------------------
    # Abstract evaluation logic
    # ------------------------------------------------------------------

    @abstractmethod
    def evaluate(self, packet: IntelligencePacket) -> RuleResult | None:
        """
        Evaluate the rule against an IntelligencePacket.

        Args:
            packet: The assembled intelligence snapshot for the symbol.

        Returns:
            A ``RuleResult`` if the rule fires, ``None`` otherwise.

        Important:
            Do not call this method directly from the rule engine.
            Use ``safe_evaluate()`` to guarantee exception safety.
        """

    # ------------------------------------------------------------------
    # Safe wrapper — used by the rule registry
    # ------------------------------------------------------------------

    @final
    def safe_evaluate(self, packet: IntelligencePacket) -> RuleResult | None:
        """
        Evaluate the rule with guaranteed exception safety.

        Wraps ``evaluate()`` in a try/except so that a buggy or misconfigured
        rule never crashes the rule engine loop. Errors are logged at ERROR
        level with the full traceback.

        This method is marked ``@final`` and must not be overridden.

        Args:
            packet: The IntelligencePacket to evaluate.

        Returns:
            A ``RuleResult`` if the rule fires, ``None`` if it does not fire
            or if an exception was caught during evaluation.
        """
        try:
            result = self.evaluate(packet)
        except Exception:
            logger.error(
                "rule_evaluation_error",
                exc_info=True,
                extra={
                    "rule_id": self.rule_id,
                    "rule_name": self.name,
                    "symbol": packet.symbol,
                },
            )
            return None

        if result is not None:
            logger.info(
                "rule_fired",
                extra={
                    "rule_id": self.rule_id,
                    "rule_name": self.name,
                    "symbol": packet.symbol,
                    "severity": result.severity.value,
                    "description": result.description,
                },
            )

        return result

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        """Return a developer-friendly string representation."""
        return f"{self.__class__.__name__}(rule_id={self.rule_id!r})"

    def __eq__(self, other: object) -> bool:
        """Rules are equal if they share the same rule_id."""
        if not isinstance(other, BaseRule):
            return NotImplemented
        return self.rule_id == other.rule_id

    def __hash__(self) -> int:
        """Hash based on rule_id for use in sets and dict keys."""
        return hash(self.rule_id)
