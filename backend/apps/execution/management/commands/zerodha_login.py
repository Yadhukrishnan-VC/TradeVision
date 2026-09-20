from django.core.management.base import BaseCommand, CommandError
from kiteconnect import KiteConnect

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

    def handle(self, *args, **options):
        request_token = options["request_token"]
        api_key = config.zerodha_api_key or "sandboxdemo"

        try:
            kite = KiteConnect(api_key=api_key)
            session = kite.generate_session(request_token)
            access_token = session["access_token"]

            # Persist the access_token so the running stack picks it up without restart.
            # Django settings are not editable at runtime via management commands,
            # so we write to the .env file and also set the in-memory config.
            import os

            env_path = "/home/yk/Documents/TradeVision/backend/.env"
            env_lines = []
            env_updated = False

            # Read existing .env and update/replace ZERODHA_ACCESS_TOKEN
            with open(env_path, "r") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped.startswith("ZERODHA_ACCESS_TOKEN="):
                        env_lines.append(f"ZERODHA_ACCESS_TOKEN={access_token}")
                        env_updated = True
                    else:
                        env_lines.append(line)

            if not env_updated:
                env_lines.append(f"ZERODHA_ACCESS_TOKEN={access_token}")

            with open(env_path, "w") as f:
                f.write("\n".join(env_lines))

            # Also update the in-memory config so the running stack picks it up
            config.zerodha_access_token = access_token

            self.stdout.write(
                self.style.SUCCESS(
                    f"Zerodha access_token persisted successfully. "
                    f"Token: {access_token}\n"
                    f"Reminder: this token expires at the next day's login-window reset. "
                    f"Run this command again tomorrow."
                )
            )

        except Exception as exc:
            raise CommandError(f"Failed to generate session: {exc}")