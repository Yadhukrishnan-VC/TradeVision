"""
Management command: wait_for_redis

Polls Redis until it responds to a PING command.
Used by the Celery worker entrypoint before starting consumer loops.

Usage::

    python manage.py wait_for_redis
    python manage.py wait_for_redis --timeout=120 --url=redis://redis:6379/0
"""

import logging
import time

import redis as redis_lib
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Poll Redis until it responds to PING."""

    help = "Wait for Redis to become available before proceeding."

    def add_arguments(self, parser: object) -> None:
        """Register optional CLI arguments."""
        parser.add_argument(
            "--timeout",
            type=int,
            default=60,
            help="Maximum seconds to wait before aborting (default: 60).",
        )
        parser.add_argument(
            "--interval",
            type=float,
            default=2.0,
            help="Seconds between PING attempts (default: 2.0).",
        )
        parser.add_argument(
            "--url",
            type=str,
            default=None,
            help="Redis URL to poll. Defaults to settings.REDIS_URL.",
        )

    def handle(self, *args: object, **options: object) -> None:
        """
        Attempt to PING Redis on a retry loop.

        Exits with code 1 (via ``CommandError``) if Redis does not respond
        within the configured timeout.
        """
        timeout: int = options["timeout"]  # type: ignore[assignment]
        interval: float = options["interval"]  # type: ignore[assignment]
        redis_url: str = options["url"] or settings.REDIS_URL  # type: ignore[assignment]
        elapsed: float = 0.0

        self.stdout.write(f"Waiting for Redis at {redis_url} (timeout={timeout}s)…")

        while elapsed < timeout:
            try:
                client: redis_lib.Redis = redis_lib.from_url(  # type: ignore[type-arg]
                    redis_url,
                    socket_connect_timeout=3,
                    socket_timeout=3,
                )
                client.ping()
                client.close()
                self.stdout.write(
                    self.style.SUCCESS(f"✓ Redis ready after {elapsed:.1f}s.")
                )
                logger.info(
                    "wait_for_redis_ready",
                    extra={"url": redis_url, "elapsed_seconds": elapsed},
                )
                return
            except (
                redis_lib.ConnectionError,
                redis_lib.TimeoutError,
                Exception,
            ) as exc:
                self.stdout.write(
                    f"  [{elapsed:.0f}s] Not ready ({exc}) — retrying in {interval}s…"
                )
                logger.debug(
                    "wait_for_redis_retry",
                    extra={
                        "url": redis_url,
                        "elapsed_seconds": elapsed,
                        "error": str(exc),
                    },
                )
                time.sleep(interval)
                elapsed += interval

        logger.error(
            "wait_for_redis_timeout",
            extra={"url": redis_url, "timeout_seconds": timeout},
        )
        raise CommandError(
            f"Redis at {redis_url} not available after {timeout}s. Aborting."
        )
