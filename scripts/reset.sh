#!/usr/bin/env bash
# =============================================================================
# TradeVision AI — Reset Script
# ⚠️  DANGER: Destroys ALL containers, volumes, and data. Dev use only.
# Run from the project root: bash scripts/reset.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
COMPOSE_DEV="docker compose -f ${PROJECT_ROOT}/docker-compose.yml -f ${PROJECT_ROOT}/docker-compose.dev.yml"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  ⚠️   TradeVision AI — RESET  ⚠️           ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "  This will permanently destroy:"
echo "    • All Docker containers"
echo "    • ALL volumes (PostgreSQL data, Redis data, static files)"
echo "    • All Docker networks for this project"
echo ""
echo "  This operation CANNOT be undone."
echo "  Take a backup first if you need to preserve any data:"
echo "    bash scripts/backup.sh"
echo ""
read -rp "  Type 'RESET' to confirm complete data destruction: " CONFIRM
echo ""

if [ "${CONFIRM}" != "RESET" ]; then
    echo "  Aborted. No changes made."
    exit 0
fi

echo "  Stopping and removing all containers, volumes, and networks..."
${COMPOSE_DEV} down --volumes --remove-orphans --timeout 10

echo ""
echo "  ✅ Reset complete."
echo "  Run 'make setup' or 'bash scripts/bootstrap.sh' to reinitialise."
echo ""
