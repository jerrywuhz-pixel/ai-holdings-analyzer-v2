#!/usr/bin/env bash
set -euo pipefail

# ============================================
# AI Holdings Analyzer 2.0 - Local Dev Init
# ============================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$PROJECT_ROOT/docker-compose.yml"
ENV_FILE="$PROJECT_ROOT/.env"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# --------------------------------------------
# Check dependencies
# --------------------------------------------
check_command() {
    if ! command -v "$1" &>/dev/null; then
        log_error "$1 is not installed. Please install it first."
        exit 1
    fi
}

log_info "Checking prerequisites..."
check_command docker
check_command docker-compose
check_command pg_isready || {
    log_warn "pg_isready not found. Will use basic connection check instead."
    HAS_PG_ISREADY=false
}

# --------------------------------------------
# Ensure .env exists
# --------------------------------------------
if [[ ! -f "$ENV_FILE" ]]; then
    if [[ -f "$PROJECT_ROOT/.env.example" ]]; then
        log_warn ".env not found. Copying from .env.example..."
        cp "$PROJECT_ROOT/.env.example" "$ENV_FILE"
    else
        log_error ".env and .env.example both missing. Please create .env manually."
        exit 1
    fi
fi

# --------------------------------------------
# Start services
# --------------------------------------------
log_info "Starting docker-compose services..."
cd "$PROJECT_ROOT"
docker-compose --file "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --build

# --------------------------------------------
# Wait for PostgreSQL
# --------------------------------------------
log_info "Waiting for PostgreSQL to be ready..."
MAX_RETRIES=30
RETRY_COUNT=0

while [[ $RETRY_COUNT -lt $MAX_RETRIES ]]; do
    if docker-compose exec -T postgres pg_isready -U postgres &>/dev/null; then
        log_info "PostgreSQL is ready!"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo -n "."
    sleep 1
done

if [[ $RETRY_COUNT -eq $MAX_RETRIES ]]; then
    log_error "PostgreSQL did not become ready in time."
    docker-compose logs postgres --tail=50
    exit 1
fi

# --------------------------------------------
# Wait for WebApp
# --------------------------------------------
log_info "Waiting for WebApp to start..."
WEBAPP_PORT=$(grep '^WEBAPP_PORT=' "$ENV_FILE" | cut -d= -f2 || echo "3000")

MAX_RETRIES_WEBAPP=60
RETRY_COUNT_WEBAPP=0

while [[ $RETRY_COUNT_WEBAPP -lt $MAX_RETRIES_WEBAPP ]]; do
    if docker-compose ps webapp | grep -q "Up"; then
        log_info "WebApp is up!"
        break
    fi
    RETRY_COUNT_WEBAPP=$((RETRY_COUNT_WEBAPP + 1))
    echo -n "."
    sleep 1
done

if [[ $RETRY_COUNT_WEBAPP -eq $MAX_RETRIES_WEBAPP ]]; then
    log_warn "WebApp did not become ready in time. Check logs with: docker-compose logs webapp"
fi

# --------------------------------------------
# Summary
# --------------------------------------------
DATA_SERVICE_PORT=$(grep '^DATA_SERVICE_PORT=' "$ENV_FILE" | cut -d= -f2 || echo "8000")

log_info "========================================"
log_info "Local development environment is ready!"
log_info "========================================"
echo ""
echo "  PostgreSQL:   postgres://postgres:postgres@localhost:5432/ai_holdings"
echo "  Redis:        redis://localhost:6379/0"
echo "  Data Service: http://localhost:${DATA_SERVICE_PORT:-8000}"
echo "  WebApp:       http://localhost:${WEBAPP_PORT:-3000}"
echo ""
echo "  Useful commands:"
echo "    docker-compose logs -f data-service"
echo "    docker-compose logs -f webapp"
echo "    docker-compose exec postgres psql -U postgres -d ai_holdings"
echo "    docker-compose down"
echo ""
