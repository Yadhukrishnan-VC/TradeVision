from __future__ import annotations

import uuid

from django.conf import settings
from django.db import migrations


def seed_default_account(apps, schema_editor) -> None:
    User = apps.get_model(settings.AUTH_USER_MODEL)
    Account = apps.get_model("accounts", "Account")

    if Account.objects.filter(is_default=True).exists():
        return

    user = User.objects.filter(is_superuser=True).first()
    if user is None:
        user = User.objects.first()

    if user is not None:
        Account.objects.get_or_create(
            is_default=True,
            defaults={
                "id": uuid.uuid4(),
                "name": "Default Trading Account",
                "owner": user,
            },
        )


def reverse_seed_default_account(apps, schema_editor) -> None:
    Account = apps.get_model("accounts", "Account")
    Account.objects.filter(is_default=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_account"),
    ]

    operations = [
        migrations.RunPython(seed_default_account, reverse_seed_default_account),
    ]
