"""
Management command: seed_admin

Creates a Django superuser from environment variables idempotently.
Safe to run multiple times — skips creation if the user already exists.

Required environment variables (with defaults for development)::

    ADMIN_EMAIL=admin@tradevision.ai
    ADMIN_PASSWORD=changeme123   ← change before production deployment

Usage::

    python manage.py seed_admin
    python manage.py seed_admin --email=ops@company.com
"""

import logging
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Create a superuser from environment variables, idempotently."""

    help = (
        "Create a Django superuser from ADMIN_EMAIL / ADMIN_PASSWORD env vars. "
        "Safe to run multiple times — skips if the account already exists."
    )

    def add_arguments(self, parser: object) -> None:
        """Register optional CLI overrides for the email address."""
        parser.add_argument(
            "--email",
            type=str,
            default=None,
            help="Override ADMIN_EMAIL environment variable.",
        )
        parser.add_argument(
            "--password",
            type=str,
            default=None,
            help=(
                "Override ADMIN_PASSWORD environment variable. "
                "Avoid passing passwords as CLI arguments in production — "
                "prefer the environment variable."
            ),
        )

    def handle(self, *args: object, **options: object) -> None:
        """
        Create the admin superuser if they do not already exist.

        Exits cleanly (no error) if the user is already present, making
        this command safe to include in Docker entrypoint scripts.
        """
        User = get_user_model()

        email: str = (
            options["email"]  # type: ignore[assignment]
            or os.environ.get("ADMIN_EMAIL", "admin@tradevision.ai")
        )
        password: str = (
            options["password"]  # type: ignore[assignment]
            or os.environ.get("ADMIN_PASSWORD", "changeme123")
        )

        if not email or not password:
            raise CommandError(
                "Both ADMIN_EMAIL and ADMIN_PASSWORD must be set "
                "(via environment variables or --email / --password flags)."
            )

        if User.objects.filter(email=email).exists():
            self.stdout.write(
                self.style.WARNING(
                    f"Superuser '{email}' already exists — skipping creation."
                )
            )
            logger.info("seed_admin_skipped", extra={"email": email})
            return

        username = self._derive_username(User, email)
        User.objects.create_superuser(username=username, email=email, password=password)

        self.stdout.write(
            self.style.SUCCESS(f"✓ Superuser created: {email}")
        )
        logger.info("seed_admin_created", extra={"email": email})

        if password == "changeme123":  # noqa: S105
            self.stdout.write(
                self.style.WARNING(
                    "⚠  Default password detected. "
                    "Set ADMIN_PASSWORD before deploying to production."
                )
            )

    @staticmethod
    def _derive_username(User: object, email: str) -> str:
        """
        Derive a unique username from the email local-part.

        Falls back to ``admin`` and appends a numeric suffix if the
        candidate is already taken (the ``User.username`` column is unique).
        """
        base = email.split("@", 1)[0].strip() or "admin"
        candidate = base
        suffix = 1
        while User.objects.filter(username=candidate).exists():
            suffix += 1
            candidate = f"{base}{suffix}"
        return candidate
