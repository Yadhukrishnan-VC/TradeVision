from __future__ import annotations

from .base import *

DEBUG = False

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

LOGGING["root"]["level"] = "INFO"

EVENT_BUS_IMPLEMENTATION = "redis"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.common.infrastructure.middleware.CorrelationIdMiddleware",
]
