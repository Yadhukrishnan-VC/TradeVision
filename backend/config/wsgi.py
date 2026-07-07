"""
TradeVision AI — WSGI application.

Used by Gunicorn in production and by Django's test client in the test suite.
Daphne (ASGI) is the primary server; this module exists as a fallback and for
management commands that rely on the WSGI application object.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

application = get_wsgi_application()
