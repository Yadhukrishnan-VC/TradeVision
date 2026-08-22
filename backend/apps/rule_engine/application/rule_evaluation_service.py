from __future__ import annotations

import logging
import uuid

from core.events.event_types import EnrichedIntelligencePacket
from django.db import models, transaction

from core.execution_context import get_account_override
from core.rules.base_rule import RuleResult
from core.rules.rule_registry import RuleRegistry
from core.services import BaseService
from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.rule_engine.domain.entities import RuleFiring
from apps.rule_engine.domain.exceptions import RuleEvaluationError
from apps.rule_engine.domain.rules import (
    BreakoutRule,
    HighBetaBreakoutRule,
    LongMomentumRule,
    PriceMovementRule,
    ShortBreakdownRule,
    ShortSellRule,
    VolatilityBreakoutRule,
    VolumeSpikeRule,
)
from apps.rule_engine.infrastructure.repositories import (
    RuleConfigRepository,
    RuleExecutionRepository,
)

logger = logging.getLogger(__name__)


class RuleEvaluationService(BaseService):
    def __init__(self) -> None:
        super().__init__()
        self._repository = RuleExecutionRepository()
        self._config_repository = RuleConfigRepository()
        self._registry = RuleRegistry()
        self._register_builtin_rules()

    def _register_builtin_rules(self) -> None:
        self._registry.register(PriceMovementRule())
        self._registry.register(VolumeSpikeRule())
        self._registry.register(BreakoutRule())
        self._registry.register(LongMomentumRule())
        self._registry.register(ShortSellRule())
        self._registry.register(VolatilityBreakoutRule())
        self._registry.register(HighBetaBreakoutRule())
        self._registry.register(ShortBreakdownRule())

    def evaluate_enriched_packet(
        self,
        enriched: EnrichedIntelligencePacket,
        analysis_event_id: uuid.UUID | None = None,
    ) -> list[RuleFiring]:
        packet = enriched.packet
        if not packet.freshness_validated:
            self._logger.info("packet_not_fresh", extra={"symbol": packet.symbol})
            return []

        results = self._registry.evaluate_all(packet)
        firings: list[RuleFiring] = []
        regime = getattr(packet, "regime", None)
        # ADR-029: live firing must clear the go/no-go validation gate.
        # Backtest replay (account override bound) always fires ungated so the
        # run can generate the RuleExecution/Fill rows validation needs.
        if get_account_override() is None:
            results = self._filter_by_gate(results, regime, symbol=packet.symbol)
        with transaction.atomic():
            for result in results:
                analysis_event = result.to_analysis_event(
                    symbol=packet.symbol,
                    packet=packet,
                )
                event_id = analysis_event_id or analysis_event.id
                trigger_data = dict(result.trigger_data)
                if regime:
                    trigger_data["regime"] = regime
                firing = RuleFiring(
                    rule_id=result.rule_id,
                    event_type=result.event_type.value,
                    severity=result.severity,
                    symbol=packet.symbol,
                    trigger_data=trigger_data,
                    analysis_event_id=event_id,
                    occurred_at=analysis_event.timestamp,
                )
                execution = self._repository.create_from_firing(firing, str(event_id))
                if execution is None:
                    continue
                firings.append(firing)

        return firings

    def _filter_by_gate(
        self, results: list[RuleResult], regime: str | None, symbol: str = ""
    ) -> list[RuleResult]:
        """ADR-029 §4 gate: keep only (rule_id, regime) pairs that are both
        enabled and validated, fail-closed for everything else.

        Exclusion reasons logged at INFO via ``rule_gated_out``: ``no_config``
        (no RuleConfig row), ``disabled`` (RuleConfig.enabled is False),
        ``no_regime`` (packet carried no regime), ``not_validated`` (regime
        has no GO/NO_GO verdict in ``validated_regimes``). Rows created by
        backtesting always have ``enabled=False`` (ADR-029 §3), so a GO verdict
        alone never flips a rule live — an explicit human decision is required.

        LIVE-PAPER-DRESS-REHEARSAL-1 exception: an owner-flagged
        ``ObservedRule`` row (apps/live_drift) bypasses the *validation*
        requirement so the rule can fire on the paper broker against live data
        and feed the drift monitor. See :meth:`_observation_paper_bypass` for
        the fail-closed conditions; nothing here writes validated_regimes.
        """
        allowed: list[RuleResult] = []
        if not regime:
            for result in results:
                logger.info(
                    "rule_gated_out",
                    extra={
                        "rule_id": result.rule_id,
                        "regime": None,
                        "reason": "no_regime",
                    },
                )
            return []

        for result in results:
            config = self._config_repository.get_by_rule_id(result.rule_id)
            if config is None:
                reason = "no_config"
            elif not config.enabled:
                reason = "disabled"
            elif self._observation_paper_bypass(result.rule_id, regime, symbol):
                # Explicit owner opt-in; paper broker only. Logged separately
                # from rule_gated_out so the audit trail distinguishes a
                # validated GO from an observation bypass.
                logger.info(
                    "rule_observation_paper_bypass",
                    extra={"rule_id": result.rule_id, "regime": regime, "symbol": symbol},
                )
                allowed.append(result)
                continue
            elif (
                regime not in config.validated_regimes
                or config.validated_regimes[regime].get("status") != "GO"
            ):
                reason = "not_validated"
            else:
                allowed.append(result)
                continue

            logger.info(
                "rule_gated_out",
                extra={
                    "rule_id": result.rule_id,
                    "regime": regime,
                    "reason": reason,
                },
            )
        return allowed

    @staticmethod
    def _observation_paper_bypass(rule_id: str, regime: str, symbol: str = "") -> bool:
        """Fail-closed check for the live-paper observation exception.

        ALL of the following must hold before a rule may fire without a
        validated-regime GO:

        - ``BROKER_ENVIRONMENT != "live"`` — this mechanism must never unlock
          real capital;
        - ``RuleConfig.enabled`` is already guaranteed by the caller's chain;
        - an **enabled** ``ObservedRule`` exists for exactly this
          ``(rule_id, regime)`` whose symbol scope covers ``symbol``
          (empty scope = any symbol; non-empty = exact match).
        """
        from django.conf import settings as dj_settings

        if str(getattr(dj_settings, "BROKER_ENVIRONMENT", "sandbox")) == "live":
            return False

        from apps.live_drift.infrastructure.models import ObservedRule

        scope_filter = models.Q(symbol="") | models.Q(symbol=symbol)
        return (
            ObservedRule.objects.filter(rule_id=rule_id, regime=regime, enabled=True)
            .filter(scope_filter)
            .exists()
        )

    def publish_rule_firing(
        self,
        firing: RuleFiring,
        account_id: uuid.UUID | None = None,
    ) -> uuid.UUID | None:
        payload = {
            "symbol": firing.symbol,
            "event_type": firing.event_type,
            "rule_id": firing.rule_id,
            "severity": firing.severity.value,
            "trigger_data": firing.trigger_data,
            "analysis_event_id": str(firing.analysis_event_id),
            "occurred_at": firing.occurred_at.isoformat(),
        }
        # Backtest replay routes the whole chain to an isolated account via an
        # optional, additive payload field; absent -> production is_default
        # resolution downstream (zero behavior change).
        if account_id is not None:
            payload["account_id"] = str(account_id)
        event = DomainEvent.create(
            event_type="rule_engine.RuleFired",
            payload=payload,
            correlation_id=firing.analysis_event_id,
        )
        try:
            bus = get_event_bus()
            bus.publish(event)
            self._repository.mark_published(
                firing.analysis_event_id, event.event_id, rule_id=firing.rule_id
            )
            return event.event_id
        except Exception as exc:
            self._logger.exception(
                "Failed to publish RuleFired event",
                extra={"rule_id": firing.rule_id, "symbol": firing.symbol},
            )
            raise RuleEvaluationError(f"Publish failed: {exc}") from exc
