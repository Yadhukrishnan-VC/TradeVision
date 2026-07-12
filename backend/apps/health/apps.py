"""
TradeVision AI — Health check application configuration.

The health app provides structured liveness and readiness probes for
Docker, load balancers, and operations dashboards. It has no models
and requires no database migrations.
"""

from django.apps import AppConfig


class HealthConfig(AppConfig):
    """Configuration for the ``apps.health`` application."""

    name = "apps.health"
    verbose_name = "Health"
    # No models — no default_auto_field needed
