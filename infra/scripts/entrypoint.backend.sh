#!/usr/bin/env bash
# =============================================================================
# TradeVision AI — Backend Entrypoint
# Runs inside the backend container before Daphne starts.
# Responsibilities:
#   1. Wait for PostgreSQL (via pgbouncer) to accept connections
#   2. Wait for Redis to respond
#   3. Run Django system checks
#   4. Apply database migrations (idempotent)
#   5. Collect static files (production only)
#   6. Exec the CMD passed by docker-compose (Daphne)
# =============================================================================
set -euo pipefail

readonly MAX_WAIT=60
readonly RETRY_INTERVAL=2

log() {
    echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] [entrypoint.backend] $*"
}

# ---------------------------------------------------------------------------
# Wait for a TCP service to become available
# Usage: wait_for_service <host> <port> <name>
# ---------------------------------------------------------------------------
wait_for_service() {
    local host="$1"
    local port="$2"
    local name="$3"
    local elapsed=0

    log "Waiting for ${name} at ${host}:${port}..."
    until bash -c "echo > /dev/tcp/${host}/${port}" 2>/dev/null; do
        if [ "${elapsed}" -ge "${MAX_WAIT}" ]; then
            log "ERROR: ${name} did not become available after ${MAX_WAIT}s. Aborting."
            exit 1
        fi
        log "  ${name} not ready — retrying in ${RETRY_INTERVAL}s (${elapsed}s elapsed)..."
        sleep "${RETRY_INTERVAL}"
        elapsed=$((elapsed + RETRY_INTERVAL))
    done
    log "${name} is ready."
}

# ---------------------------------------------------------------------------
# Wait for PostgreSQL via pgbouncer
# ---------------------------------------------------------------------------
PGBOUNCER_HOST="${POSTGRES_HOST:-pgbouncer}"
PGBOUNCER_PORT="${POSTGRES_PORT:-6432}"
wait_for_service "${PGBOUNCER_HOST}" "${PGBOUNCER_PORT}" "PostgreSQL/pgbouncer"

# Confirm pg_isready at the Postgres level (available in python:3.12 image
# because postgresql-client is installed in the Dockerfile)
POSTGRES_DIRECT_HOST="${PGBOUNCER_HOST}"
until pg_isready -h "${POSTGRES_DIRECT_HOST}" -p "${PGBOUNCER_PORT}" \
    -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -q; do
    log "  pg_isready not yet responding — waiting..."
    sleep "${RETRY_INTERVAL}"
done
log "PostgreSQL accepting connections."

# ---------------------------------------------------------------------------
# Wait for Redis
# ---------------------------------------------------------------------------
REDIS_HOST=$(echo "${REDIS_URL:-redis://redis:6379/0}" | sed 's|redis://||' | cut -d: -f1)
REDIS_PORT=$(echo "${REDIS_URL:-redis://redis:6379/0}" | sed 's|redis://||' | cut -d: -f2 | cut -d/ -f1)
wait_for_service "${REDIS_HOST}" "${REDIS_PORT}" "Redis"

until redis-cli -u "${REDIS_URL:-redis://redis:6379/0}" ping | grep -q PONG; do
    log "  Redis PING not responding — waiting..."
    sleep "${RETRY_INTERVAL}"
done
log "Redis is ready."

# ---------------------------------------------------------------------------
# Django system check
# ---------------------------------------------------------------------------
log "Running Django system checks..."
python manage.py check --deploy 2>/dev/null || python manage.py check

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