"""PORTFOLIO-DAILY-CAPITAL — daily capital reset (Celery task).

``reset_daily_capital`` re-applies the operator-configured daily capital
(``PORTFOLIO_DAILY_CAPITAL``) to the primary account each morning, before the
market opens. It routes through ``CapitalService.set_daily_capital`` so the
day's P&L is swept into/out of cash via the same ledger path as the API
endpoint (``SetDailyCapitalView``) — one source of truth for "how much is
there to trade with today".

No-ops (never fails the beat) when:
    * ``PORTFOLIO_DAILY_CAPITAL`` is empty/zero (resets are opt-in), or
    * no primary (``is_default``) account exists yet.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any

from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(
    queue="maintenance",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    soft_time_limit=120,
    time_limit=180,
)
def reset_daily_capital(*, account_id: str | None = None) -> dict[str, Any]:
    """Apply ``PORTFOLIO_DAILY_CAPITAL`` to the primary account's cash.

    Schedule: Beat runs this before market open (IST 08:30). Re-runs are
    idempotent — ``set_daily_capital`` with ``target == cash`` is a no-op.

    Returns a small outcome dict for observability; raises nothing on the
    plausible no-op cases (disabled config, no primary account).
    """
    daily = getattr(settings, "PORTFOLIO_DAILY_CAPITAL", Decimal(0)) or Decimal(0)
    if daily <= 0:
        logger.info("portfolio_daily_capital_disabled")
        return {"applied": False, "reason": "disabled"}

    from apps.accounts.infrastructure.models import Account
    from apps.portfolio.application.capital_service import CapitalService

    if account_id:
        target_account = Account.objects.filter(pk=account_id).first()
    else:
        target_account = (
            Account.objects.filter(is_default=True).order_by("-created_at").first()
        )
    if target_account is None:
        logger.info("portfolio_daily_capital_no_primary_account")
        return {"applied": False, "reason": "no-primary-account"}

    service = CapitalService()
    state = service.set_daily_capital(
        account_id=target_account.id,
        target_cash=daily,
        correlation_id=uuid.uuid4(),
    )
    logger.info(
        "portfolio_daily_capital_applied",
        extra={
            "account_id": str(target_account.id),
            "target_cash": str(daily),
            "cash": str(state.cash),
            "available_capital": str(state.available_capital),
        },
    )
    return {
        "applied": True,
        "account_id": str(target_account.id),
        "cash": str(state.cash),
        "available_capital": str(state.available_capital),
    }