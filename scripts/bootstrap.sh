#!/usr/bin/env bash
# =============================================================================
# TradeVision AI — Bootstrap Script
# First-time project setup: copies .env, builds images, runs migrations.
# Run from the project root: bash scripts/bootstrap.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
COMPOSE_DEV="docker compose -f ${PROJECT_ROOT}/docker-compose.yml -f ${PROJECT_ROOT}/docker-compose.dev.yml"

log() { echo "  $*"; }
section() { echo ""; echo "── $* ──────────────────────────────────────"; }

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║     TradeVision AI — Bootstrap           ║"
echo "╚══════════════════════════════════════════╝"

# ---------------------------------------------------------------------------
# Verify .env exists; guide the user if not
# ---------------------------------------------------------------------------
section "Environment"
if [ ! -f "${PROJECT_ROOT}/.env" ]; then
    log ".env not found — creating from .env.example..."
    cp "${PROJECT_ROOT}/.env.example" "${PROJECT_ROOT}/.env"
    echo ""
    echo "  ⚠️  A .env file has been created from .env.example."
    echo "  ⚠️  Edit it with real values before continuing:"
    echo "      ${PROJECT_ROOT}/.env"
    echo ""
    echo "  At minimum, set:"
    echo "    POSTGRES_PASSWORD=<strong-password>"
    echo "    DJANGO_SECRET_KEY=<50-char-random-string>"
    echo "    GEMINI_API_KEY=<your-gemini-api-key>  (or chosen AI provider)"
    echo ""
    read -rp "  Press ENTER when .env is ready, or Ctrl-C to abort: "
fi
log ".env found ✓"

# ---------------------------------------------------------------------------
# Build images
# ---------------------------------------------------------------------------
section "Building Docker images"
${COMPOSE_DEV} build --parallel
log "Images built ✓"

# ---------------------------------------------------------------------------
# Start infrastructure services first (postgres, redis) and let them stabilise
# ---------------------------------------------------------------------------
section "Starting infrastructure services"
${COMPOSE_DEV} up -d postgres redis
log "Waiting 15s for PostgreSQL and Redis to initialise..."
sleep 15
log "Infrastructure ready ✓"

# ---------------------------------------------------------------------------
# Start all services
# ---------------------------------------------------------------------------
section "Starting all services"
${COMPOSE_DEV} up -d
log "Waiting 20s for backend to complete migrations..."
sleep 20

# ---------------------------------------------------------------------------
# Create superuser interactively
# ---------------------------------------------------------------------------
section "Django superuser"
log "Creating Django superuser (interactive)..."
${COMPOSE_DEV} exec backend python manage.py createsuperuser

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║     Bootstrap complete ✅                 ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "  Services:"
echo "    Frontend:    http://localhost"
echo "    API:         http://localhost/api/v1/"
echo "    Django Admin:http://localhost/admin/"
echo "    Flower:      http://localhost:5555"
echo ""
echo "  Useful commands:"
echo "    make logs          — follow all logs"
echo "    make shell         — Django shell"
echo "    make test          — run test suite"
echo ""
