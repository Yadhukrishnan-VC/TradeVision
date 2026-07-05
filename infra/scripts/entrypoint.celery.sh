#!/usr/bin/env bash
# =============================================================================
# TradeVision AI — Celery Worker / Beat Entrypoint
# Runs inside all celery-* containers before the worker process starts.
# Responsibilities:
#   1. Wait for Redis (broker) to respond
#   2. Wait for PostgreSQL (via pgbouncer) — workers read/write the database
#   3. Exec the CMD passed by docker-compose (celery worker or beat)
# =============================================================================
set -euo pipefail

readonly MAX_WAIT=60
readonly RETRY_INTERVAL=2

log() {
    echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] [entrypoint.celery] $*"
}

# ---------------------------------------------------------------------------
# Wait for a TCP service to become available
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
# Wait for Redis — primary concern for Celery (it's the broker)
# ---------------------------------------------------------------------------
REDIS_HOST=$(echo "${REDIS_URL:-redis://redis:6379/0}" | sed 's|redis://||' | cut -d: -f1)
REDIS_PORT=$(echo "${REDIS_URL:-redis://redis:6379/0}" | sed 's|redis://||' | cut -d: -f2 | cut -d/ -f1)
wait_for_service "${REDIS_HOST}" "${REDIS_PORT}" "Redis"

until redis-cli -u "${REDIS_URL:-redis://redis:6379/0}" ping | grep -q PONG; do
    log "  Redis PING not yet responding — waiting..."
    sleep "${RETRY_INTERVAL}"
done
log "Redis broker is ready."

# ---------------------------------------------------------------------------
# Wait for PostgreSQL — workers run ORM queries
# ---------------------------------------------------------------------------
PGBOUNCER_HOST="${POSTGRES_HOST:-pgbouncer}"
PGBOUNCER_PORT="${POSTGRES_PORT:-6432}"
wait_for_service "${PGBOUNCER_HOST}" "${PGBOUNCER_PORT}" "PostgreSQL/pgbouncer"
log "PostgreSQL is reachable."

# ---------------------------------------------------------------------------
# Hand off to the CMD specified in docker-compose (celery worker or beat)
# ---------------------------------------------------------------------------
log "Starting Celery process: $*"
exec "$@"
