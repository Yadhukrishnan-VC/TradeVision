#!/usr/bin/env bash
# =============================================================================
# TradeVision AI — Backend Entrypoint
# Runs inside the backend container before Daphne starts.
# Responsibilities:
#   1. Wait for PostgreSQL (via Django management command — better error messages)
#   2. Wait for Redis    (via Django management command)
#   3. Run system check  (via Django management command)
#   4. Apply database migrations (idempotent)
#   5. Collect static files (production only)
#   6. Exec the CMD passed by docker-compose (Daphne)
# =============================================================================
set -euo pipefail

log() {
    echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] [entrypoint.backend] $*"
}

# ---------------------------------------------------------------------------
# Wait for PostgreSQL
# Delegates to apps.common.management.commands.wait_for_db which polls
# Django's database connection — richer error messages than a TCP probe.
# ---------------------------------------------------------------------------
log "Waiting for PostgreSQL..."
python manage.py wait_for_db --timeout=60
log "PostgreSQL is ready."

# ---------------------------------------------------------------------------
# Wait for Redis
# Delegates to apps.common.management.commands.wait_for_redis which sends
# a PING via the redis-py client used everywhere else in the codebase.
# ---------------------------------------------------------------------------
log "Waiting for Redis..."
python manage.py wait_for_redis --timeout=60
log "Redis is ready."

# ---------------------------------------------------------------------------
# System check
# Runs apps.common.management.commands.system_check which re-verifies DB
# and Redis are both healthy before migrations or the server start.
# ---------------------------------------------------------------------------
log "Running system checks..."
python manage.py system_check --skip-celery

# ---------------------------------------------------------------------------
# Database migrations (always safe to run — idempotent)
# ---------------------------------------------------------------------------
log "Applying database migrations..."
python manage.py migrate --no-input

# ---------------------------------------------------------------------------
# Collect static files (production only)
# ---------------------------------------------------------------------------
if [ "${DJANGO_SETTINGS_MODULE:-}" = "config.settings.production" ]; then
    log "Collecting static files..."
    python manage.py collectstatic --no-input --clear
fi

# ---------------------------------------------------------------------------
# Hand off to the CMD specified in docker-compose (Daphne)
# ---------------------------------------------------------------------------
log "Starting application: $*"
exec "$@"
