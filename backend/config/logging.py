from __future__ import annotations

import logging.config

from apps.common.infrastructure.logging_context import CorrelationIdFilter


LOGGING: dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "correlation_id": {
            "()": CorrelationIdFilter,
        },
    },
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "fmt": "%(asctime)s %(name)s %(levelname)s %(message)s %(correlation_id)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["correlation_id"],
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}
