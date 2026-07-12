"""
Management command: system_check

Verifies that all required external services (DB, Redis, Celery) are
operational and reports a structured status summary. Exits non-zero if any
critical service is unavailable.

Usage::

    python manage.py system_check
    python manage.py system_check --skip-celery
"""

import logging
import time

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

_OK = "✓"
_FAIL = "✗"
_WARN = "⚠"


class Command(BaseCommand):
    """Run structured health checks against all system dependencies."""

    help = "Check database, Redis, and Celery connectivity and report status."

    def add_arguments(self, parser: object) -> None:
        """Register optional CLI arguments."""
        parser.add_argument(
            "--skip-celery",
            action="store_true",
            default=False,
            help="Skip the Celery worker check (useful in one-off tasks).",
        )

    def handle(self, *args: object, **options: object) -> None:
        """
        Run all checks and write a summary to stdout.

        Exits with code 1 if any critical check fails.
        """
        skip_celery: bool = options["skip_celery"]  # type: ignore[assignment]
        failed: list[str] = []

        self.stdout.write("\nTradeVision AI — System Check\n" + "=" * 40)

        # ------------------------------------------------------------------
        # Database
        # ------------------------------------------------------------------
        start = time.monotonic()
        try:
            from django.db import connection

            connection.ensure_connection()
            latency = (time.monotonic() - start) * 1000
            self.stdout.write(
                self.style.SUCCESS(f"{_OK} Database        ({latency:.1f} ms)")
            )
            logger.info("system_check_db_ok", extra={"latency_ms": latency})
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"{_FAIL} Database        {exc}"))
            logger.error("system_check_db_fail", extra={"error": str(exc)})
            failed.append("database")

        # ------------------------------------------------------------------
        # Redis
        # ------------------------------------------------------------------
        start = time.monotonic()
        try:
            import redis as redis_lib
            from django.conf import settings

            client: redis_lib.Redis = redis_lib.from_url(  # type: ignore[type-arg]
                settings.REDIS_URL, socket_connect_timeout=3
            )
            client.ping()
            client.close()
            latency = (time.monotonic() - start) * 1000
            self.stdout.write(
                self.style.SUCCESS(f"{_OK} Redis           ({latency:.1f} ms)")
            )
            logger.info("system_check_redis_ok", extra={"latency_ms": latency})
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"{_FAIL} Redis           {exc}"))
            logger.error("system_check_redis_fail", extra={"error": str(exc)})
            failed.append("redis")

        # ------------------------------------------------------------------
        # Celery (optional — degraded, not critical)
        # ------------------------------------------------------------------
        if not skip_celery:
            start = time.monotonic()
            try:
                from config.celery import app as celery_app

                inspector = celery_app.control.inspect(timeout=3.0)
                ping = inspector.ping()
                latency = (time.monotonic() - start) * 1000
                if ping:
                    worker_count = len(ping)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"{_OK} Celery          ({latency:.1f} ms, {worker_count} worker(s))"
                        )
                    )
                    logger.info(
                        "system_check_celery_ok",
                        extra={"latency_ms": latency, "workers": worker_count},
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f"{_WARN} Celery          No workers responded")
                    )
                    logger.warning("system_check_celery_no_workers")
            except Exception as exc:
                self.stdout.write(
                    self.style.WARNING(f"{_WARN} Celery          {exc} (non-critical)")
                )
                logger.warning("system_check_celery_warn", extra={"error": str(exc)})
        else:
            self.stdout.write(f"  Celery          skipped (--skip-celery)")

        # ------------------------------------------------------------------
        # Summary
        # ------------------------------------------------------------------
        self.stdout.write("=" * 40)
        if failed:
            self.stdout.write(
                self.style.ERROR(
                    f"\n{_FAIL} System check FAILED: {', '.join(failed)}\n"
                )
            )
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS(f"\n{_OK} All critical checks passed.\n"))
        logger.info("system_check_passed")
