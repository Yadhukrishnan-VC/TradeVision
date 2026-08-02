from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender="accounts.Account")
def account_capital_created(sender, instance, created: bool, **kwargs) -> None:  # noqa: ARG001
    """Create the zero-balance ``AccountCapitalState`` alongside ``Account``.

    ADR-028 §19: ``Account`` created -> ``AccountCapitalState`` row created
    alongside it (zero-balance by default). ``apps.accounts`` is never
    touched — this is a purely additive, one-to-one related table.
    """
    if not created:
        return
    from apps.portfolio.infrastructure.repositories import AccountCapitalRepository

    try:
        AccountCapitalRepository().get_or_create_for_account(instance.id)
    except Exception:
        logger.exception(
            "portfolio_account_capital_creation_failed",
            extra={"account_id": str(instance.id)},
        )
        raise
