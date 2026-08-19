from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from celery import shared_task
from django.db import transaction

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.risk_management.application.kill_switch_service import KillSwitchService
from apps.risk_management.application.risk_evaluation_service import (
    RiskEvaluationService,
)
from apps.risk_management.domain.events import RiskApproved, RiskRejected
from apps.risk_management.gateways.factory import (
    get_capital_gateway,
    get_portfolio_state_gateway,
)
from apps.risk_management.gateways.market_calendar_status_gateway import (
    MarketCalendarStatusGateway,
)
from apps.risk_management.infrastructure.repositories import RiskDecisionRepository
from core.clock import get_clock
from core.tasks.base import DEFAULT_MAX_RETRIES, DEFAULT_RETRY_DELAY, BaseTask

logger = logging.getLogger(__name__)


def _optional_account_id(account_id: str | None) -> uuid.UUID | None:
    if not account_id:
        return None
    try:
        return uuid.UUID(str(account_id))
    except (ValueError, TypeError, AttributeError):
        return None


@shared_task(
    name="tradevision.risk_management.evaluate_rule_firing",
    queue="decisions",
    bind=True,
    base=BaseTask,
    max_retries=DEFAULT_MAX_RETRIES,
    default_retry_delay=DEFAULT_RETRY_DELAY,
)
def evaluate_rule_firing(
    self,
    symbol: str,
    rule_id: str,
    event_type: str,
    trigger_data: dict,
    analysis_event_id: str,
    occurred_at: str,
    rule_fired_event_id: str,
    account_id: str = "",
) -> dict:
    """Evaluate a RuleFired payload into a risk decision and publish it.

    Idempotency: the (analysis_event_id, rule_id) UniqueConstraint means a
    redelivered event produces a duplicate ``RiskDecisionExecution`` which is
    caught and skipped — never a double-published decision.
    """
    from apps.risk_management.application.risk_config import risk_config_from_settings

    account_uuid = _optional_account_id(account_id)
    service = RiskEvaluationService(
        capital_gateway=get_capital_gateway(account_uuid),
        portfolio_gateway=get_portfolio_state_gateway(account_uuid),
        market_gateway=MarketCalendarStatusGateway(),
        kill_switch_service=KillSwitchService(),
        config=risk_config_from_settings(),
    )

    reference_dt = get_clock().now()
    payload = {
        "symbol": symbol,
        "rule_id": rule_id,
        "event_type": event_type,
        "trigger_data": trigger_data,
        "analysis_event_id": analysis_event_id,
        "occurred_at": occurred_at or reference_dt.isoformat(),
    }

    decision = service.evaluate_rule_firing(payload, reference_dt=reference_dt)

    correlation_id = uuid.UUID(analysis_event_id) if analysis_event_id else uuid.uuid4()
    causation_id = uuid.UUID(rule_fired_event_id) if rule_fired_event_id else None

    with transaction.atomic():
        execution = RiskDecisionRepository().create_from_decision(
            decision, analysis_event_id
        )
        if execution is None:
            logger.warning(
                "duplicate_risk_evaluation_skipped",
                extra={"analysis_event_id": analysis_event_id, "rule_id": rule_id},
            )
            return {"status": "skipped_duplicate", "rule_id": rule_id}

        event = _build_decision_event(decision, correlation_id, causation_id, account_id=account_id)
        try:
            bus = get_event_bus()
            bus.publish(event)
            RiskDecisionRepository().mark_published(
                decision.analysis_event_id, event.event_id, rule_id=decision.rule_id
            )
        except Exception:
            logger.exception(
                "risk_decision_publish_failed",
                extra={"rule_id": rule_id, "symbol": symbol},
            )
            raise

    return {
        "status": decision.status.value,
        "rule_id": rule_id,
        "symbol": symbol,
        "published_event_id": str(event.event_id),
    }


def _build_decision_event(
    decision,
    correlation_id: uuid.UUID,
    causation_id: uuid.UUID | None,
    account_id: str = "",
) -> DomainEvent:
    if decision.rejection is not None:
        payload_obj = RiskRejected.from_decision(decision)
        event_type = "risk_management.RiskRejected"
    else:
        payload_obj = RiskApproved.from_decision(decision)
        event_type = "risk_management.RiskApproved"

    payload = payload_obj.to_payload()
    if account_id:
        payload["account_id"] = str(account_id)

    return DomainEvent.create(
        event_type=event_type,
        payload=payload,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )


@shared_task(
    name="tradevision.risk_management.evaluate_drawdown_kill_switch",
    queue="maintenance",
    bind=True,
    base=BaseTask,
    max_retries=DEFAULT_MAX_RETRIES,
    default_retry_delay=DEFAULT_RETRY_DELAY,
)
def evaluate_drawdown_kill_switch(self, account_id: str = "") -> dict:
    """Auto-activate the ACCOUNT kill switch on a realized drawdown breach.

    Scheduled on the Celery beat. Reads the portfolio/capital gateways, computes
    daily/weekly loss as a share of capital, and calls
    :meth:`KillSwitchService.evaluate_drawdown_limits` when thresholds are
    configured. A trip persists a ``KillSwitchState`` row and publishes
    ``KillSwitchActivated``, which the audit-log ``*`` subscriber records for
    free. Idempotent: an already-active ACCOUNT scope is returned as-is.
    """
    from apps.risk_management.application.risk_config import risk_config_from_settings

    account_uuid = _optional_account_id(account_id)
    config = risk_config_from_settings()
    capital = get_capital_gateway(account_uuid).get_available_capital()
    portfolio = get_portfolio_state_gateway(account_uuid)

    state = KillSwitchService().evaluate_drawdown_limits(
        daily_loss=portfolio.get_daily_loss(),
        weekly_loss=portfolio.get_weekly_loss(),
        capital=capital if capital is not None else Decimal(0),
        max_daily_loss_pct=config.max_daily_loss_pct,
        max_weekly_loss_pct=config.max_weekly_loss_pct,
    )

    if state is not None:
        logger.info(
            "drawdown_kill_switch_active",
            extra={
                "state_id": str(state.id),
                "reason": state.reason,
                "capital": str(capital),
            },
        )

    return {
        "tripped": state is not None,
        "account_id": account_uuid or "default",
        "daily_loss": str(portfolio.get_daily_loss()),
        "weekly_loss": str(portfolio.get_weekly_loss()),
        "capital": str(capital),
    }
