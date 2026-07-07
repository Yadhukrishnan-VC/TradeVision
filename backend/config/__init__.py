"""
TradeVision AI — Django configuration package.

Importing the Celery application here ensures Django's auto-discovery
picks up tasks registered in all installed applications.
"""

from .celery import app as celery_app

__all__ = ["celery_app"]
