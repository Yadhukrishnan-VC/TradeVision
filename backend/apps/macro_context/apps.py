from __future__ import annotations

from django.apps import AppConfig


class MacroContextConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.macro_context"
    label = "macro_context"
    verbose_name = "Macro Context"
