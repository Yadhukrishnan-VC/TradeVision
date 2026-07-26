from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3},
    retry_backoff=True,
    retry_backoff_max=600,
    soft_time_limit=60,
    time_limit=120,
)
def purge_expired_tokens(self: object) -> None:
    """Housekeeping task that purges expired JWT refresh tokens.

    Deletes blacklisted and expired tokens from simplejwt's
    OutstandingToken and BlacklistedToken tables.

    Runs daily at off-peak hours (03:00 IST).
    """
    try:
        from rest_framework_simplejwt.token_blacklist.models import (
            BlacklistedToken,
            OutstandingToken,
        )
    except ImportError:
        logger.warning("djangorestframework-simplejwt token_blacklist not installed")
        return

    from django.utils import timezone

    deleted_outstanding, _ = OutstandingToken.objects.filter(
        expires_at__lte=timezone.now(),
    ).delete()

    deleted_blacklisted, _ = BlacklistedToken.objects.filter(
        token__expires_at__lte=timezone.now(),
    ).delete()

    logger.info(
        "Purged expired tokens",
        extra={
            "outstanding_tokens_deleted": deleted_outstanding,
            "blacklisted_tokens_deleted": deleted_blacklisted,
        },
    )
