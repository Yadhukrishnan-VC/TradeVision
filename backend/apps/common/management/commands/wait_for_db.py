"""
Management command: wait_for_db

Polls the default database connection until it is ready to accept queries.
Used by the backend entrypoint script before running migrations and starting
Daphne, replacing the less reliable bash TCP probe.

Usage::

    python manage.py wait_for_db
    python manage.py wait_for_db --timeout=120 --interval=3
"""

import logging
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.db.utils import OperationalError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Poll the configured database until it accepts connections."""

    help = "Wait for the database to become available before proceeding."

    def add_arguments(self, parser: object) -> None:
        """Register optional CLI arguments."""
        parser.add_argument(
            "--timeout",
            type=int,
            default=60,
            help="Maximum number of seconds to wait before aborting (default: 60).",
        )
        parser.add_argument(
            "--interval",
            type=float,
            default=2.0,
            help="Seconds between connection attempts (default: 2.0).",
        )
        parser.add_argument(
            "--alias",
            type=str,
            default="default",
            help='Database alias to poll (default: "default").',
        )

    def handle(self, *args: object, **options: object) -> None:
        """
        Attempt to connect to the database on a retry loop.

        Exits with code 1 (via ``CommandError``) if the database is not
        available within the configured timeout.
        """
        timeout: int = options["timeout"]  # type: ignore[assignment]
        interval: float = options["interval"]  # type: ignore[assignment]
        alias: str = options["alias"]  # type: ignore[assignment]
        elapsed: float = 0.0

        self.stdout.write(f"Waiting for database alias='{alias}' (timeout={timeout}s)…")

        while elapsed < timeout:
            try:
                conn = connections[alias]
                conn.ensure_connection()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ Database ready after {elapsed:.1f}s."
                    )
                )
                logger.info(
                    "wait_for_db_ready",
                    extra={"alias": alias, "elapsed_seconds": elapsed},
                )
                return
            except OperationalError as exc:
                self.stdout.write(
                    f"  [{elapsed:.0f}s] Not ready ({exc}) — retrying in {interval}s…"
                )
                logger.debug(
                    "wait_for_db_retry",
                    extra={
                        "alias": alias,
                        "elapsed_seconds": elapsed,
                        "error": str(exc),
                    },
                )
                time.sleep(interval)
                elapsed += interval

        logger.error(
            "wait_for_db_timeout",
            extra={"alias": alias, "timeout_seconds": timeout},
        )
        raise CommandError(
            f"Database alias='{alias}' not available after {timeout}s. Aborting."
        )
