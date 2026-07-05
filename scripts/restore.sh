#!/usr/bin/env bash
# =============================================================================
# TradeVision AI — Restore Script
# Restores PostgreSQL from a compressed SQL backup file.
# Usage: bash scripts/restore.sh <path-to-postgres-backup.sql.gz>
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
BACKUP_DIR="${PROJECT_ROOT}/backups"
COMPOSE_DEV="docker compose -f ${PROJECT_ROOT}/docker-compose.yml -f ${PROJECT_ROOT}/docker-compose.dev.yml"

log() { echo "  [$(date -u '+%H:%M:%S')] $*"; }

# Load environment variables
set -a
# shellcheck source=/dev/null
source "${PROJECT_ROOT}/.env"
set +a

POSTGRES_BACKUP="${1:-}"

# ---------------------------------------------------------------------------
# Guard: require a backup file argument
# ---------------------------------------------------------------------------
if [ -z "${POSTGRES_BACKUP}" ]; then
    echo ""
    echo "Usage: bash scripts/restore.sh <postgres_backup.sql.gz>"
    echo ""
    echo "Available backups:"
    if ls "${BACKUP_DIR}"/postgres_*.sql.gz 1>/dev/null 2>&1; then
        ls -lh "${BACKUP_DIR}"/postgres_*.sql.gz
    else
        echo "  (none found in ${BACKUP_DIR})"
    fi
    echo ""
    exit 1
fi

if [ ! -f "${POSTGRES_BACKUP}" ]; then
    echo "ERROR: Backup file not found: ${POSTGRES_BACKUP}"
    exit 1
fi

# ---------------------------------------------------------------------------
# Confirmation gate — this is a destructive operation
# ---------------------------------------------------------------------------
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║     TradeVision AI — Restore             ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "  ⚠️  WARNING: This will OVERWRITE the current database."
echo ""
echo "  Restore source : ${POSTGRES_BACKUP}"
echo "  Target database: ${POSTGRES_DB}"
echo ""
read -rp "  Type 'RESTORE' to confirm: " CONFIRM
echo ""

if [ "${CONFIRM}" != "RESTORE" ]; then
    echo "  Aborted. No changes made."
    exit 0
fi

# ---------------------------------------------------------------------------
# Stop the backend and workers to prevent writes during restore
# ---------------------------------------------------------------------------
log "Stopping application services..."
${COMPOSE_DEV} stop backend celery-worker-market celery-worker-ai celery-worker-default celery-beat

# ---------------------------------------------------------------------------
# Drop and recreate the database, then restore
# ---------------------------------------------------------------------------
log "Dropping and recreating database..."
${COMPOSE_DEV} exec -T postgres \
    psql --username="${POSTGRES_USER}" --dbname=postgres \
    --command="DROP DATABASE IF EXISTS ${POSTGRES_DB};" \
    --command="CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_USER};"

log "Restoring from ${POSTGRES_BACKUP}..."
gunzip -c "${POSTGRES_BACKUP}" \
    | ${COMPOSE_DEV} exec -T postgres \
    psql --username="${POSTGRES_USER}" --dbname="${POSTGRES_DB}" \
    --quiet

log "Restore complete ✓"

# ---------------------------------------------------------------------------
# Restart application services
# ---------------------------------------------------------------------------
log "Restarting application services..."
${COMPOSE_DEV} start backend celery-worker-market celery-worker-ai celery-worker-default celery-beat

echo ""
echo "  ✅ Database restored successfully."
echo "  Run 'make logs-backend' to confirm the application started cleanly."
echo ""
