import os

from django.core.management.base import BaseCommand, CommandError

from apps.execution.application.zerodha_session_service import (
    active_env_path,
    exchange_request_token,
)
from core.config import config


class Command(BaseCommand):
    help = (
        "Exchange the Kite Connect request_token for an access_token and persist it.\n"
        "Run once per trading day — the access_token expires at the next day's "
        "login-window reset (not 24h rolling)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "request_token",
            type=str,
            help="Single-use request_token obtained from the Kite login URL",
        )
        parser.add_argument(
            "--env-path",
            default=None,
            help="Target .env file to update (defaults to the active env file).",
        )

    def handle(self, *args, **options):
        if options.get("env_path"):
            os.environ["ZERODHA_ENV_FILE"] = options["env_path"]

        try:
            access_token = exchange_request_token(options["request_token"])
        except Exception as exc:
            raise CommandError(f"Failed to generate session: {exc}")

        env_path = active_env_path()
        self.stdout.write(
            self.style.SUCCESS(
                f"Zerodha access_token obtained (environment={config.broker_environment}).\n"
                f"ZERODHA_ACCESS_TOKEN={access_token}\n"
                f"Persisted to: {env_path or '<redis-hot>'}\n"
                f"Reminder: this token expires at the next day's login-window "
                f"reset. A container recreate (make up) reads it from the env "
                f"file; until then the Redis hot override already supplies it."
            )
        )