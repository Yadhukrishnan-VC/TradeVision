#!/usr/bin/env bash
# =============================================================================
# TradeVision AI — Backup Script
# Creates timestamped backups of PostgreSQL and Redis data.
# Run from the project root: bash scripts/backup.sh
# Backup files are written to: ./backups/
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
BACKUP_DIR="${PROJECT_ROOT}/backups"
TIMESTAMP="$(date -u '+%Y%m%d_%H%M%S')"
COMPOSE_DEV="docker compose -f ${PROJECT_ROOT}/docker-compose.yml -f ${PROJECT_ROOT}/docker-compose.dev.yml"

log() { echo "  [$(date -u '+%H:%M:%S')] $*"; }

# Load environment variables for POSTGRES_* references
set -a
# shellcheck source=/dev/null
source "${PROJECT_ROOT}/.env"
set +a

mkdir -p "${BACKUP_DIR}"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║     TradeVision AI — Backup              ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "  Timestamp : ${TIMESTAMP}"
echo "  Output dir: ${BACKUP_DIR}"
echo ""

# ---------------------------------------------------------------------------
# PostgreSQL — compressed SQL dump
# ---------------------------------------------------------------------------
log "Backing up PostgreSQL (${POSTGRES_DB})..."
PG_BACKUP="${BACKUP_DIR}/postgres_${TIMESTAMP}.sql.gz"

${COMPOSE_DEV} exec -T postgres \
    pg_dump \
    --username="${POSTGRES_USER}" \
    --dbname="${POSTGRES_DB}" \
    --format=plain \
    --no-owner \
    --no-acl \
    | gzip > "${PG_BACKUP}"

PG_SIZE="$(du -sh "${PG_BACKUP}" | cut -f1)"
log "PostgreSQL backup complete: $(basename "${PG_BACKUP}") (${PG_SIZE}) ✓"

# ---------------------------------------------------------------------------
# Redis — trigger BGSAVE, then copy the RDB file
# ---------------------------------------------------------------------------
log "Backing up Redis..."
REDIS_BACKUP="${BACKUP_DIR}/redis_${TIMESTAMP}.rdb"

${COMPOSE_DEV} exec -T redis redis-cli BGSAVE > /dev/null
# Wait for background save to complete (up to 30s)
for i in $(seq 1 15); do
    STATUS="$(${COMPOSE_DEV} exec -T redis redis-cli LASTSAVE)"
    sleep 2
    NEW_STATUS="$(${COMPOSE_DEV} exec -T redis redis-cli LASTSAVE)"
    if [ "${NEW_STATUS}" != "${STATUS}" ]; then
        break
    fi
done
${COMPOSE_DEV} cp redis:/data/dump.rdb "${REDIS_BACKUP}"
REDIS_SIZE="$(du -sh "${REDIS_BACKUP}" | cut -f1)"
log "Redis backup complete: $(basename "${REDIS_BACKUP}") (${REDIS_SIZE}) ✓"

# ---------------------------------------------------------------------------
# Cleanup old backups — retain last 7 days
# ---------------------------------------------------------------------------
log "Removing backups older than 7 days..."
find "${BACKUP_DIR}" -name "postgres_*.sql.gz" -mtime +7 -delete
find "${BACKUP_DIR}" -name "redis_*.rdb" -mtime +7 -delete
log "Cleanup complete ✓"

echo ""
echo "  Backup files saved to: ${BACKUP_DIR}"
echo ""
