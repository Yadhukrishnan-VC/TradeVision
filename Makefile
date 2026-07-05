# =============================================================================
# TradeVision AI — Makefile
# Run `make help` to see all available commands.
# =============================================================================

.DEFAULT_GOAL := help

# Compose file sets
COMPOSE_DEV  := docker compose -f docker-compose.yml -f docker-compose.dev.yml
COMPOSE_PROD := docker compose -f docker-compose.yml -f docker-compose.prod.yml

# Shorthand for running commands inside the backend container
BACKEND := $(COMPOSE_DEV) exec backend
FRONTEND := $(COMPOSE_DEV) exec frontend

# Colours for help output
CYAN  := \033[36m
RESET := \033[0m

.PHONY: help \
        build up up-d down restart logs logs-backend logs-celery ps \
        shell bash \
        migrate makemigrations showmigrations createsuperuser collectstatic \
        test test-fast test-cov lint format type-check pre-commit-install \
        frontend-install frontend-build \
        flower \
        setup clean nuke \
        backup restore

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
help: ## Show this help message
	@echo ""
	@echo "TradeVision AI — Development Commands"
	@echo "======================================"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-22s$(RESET) %s\n", $$1, $$2}'
	@echo ""

# ---------------------------------------------------------------------------
# Docker — Stack Management
# ---------------------------------------------------------------------------
build: ## Build all Docker images (dev)
	$(COMPOSE_DEV) build

up: ## Start all services in the foreground
	$(COMPOSE_DEV) up

up-d: ## Start all services in the background
	$(COMPOSE_DEV) up -d

down: ## Stop all services
	$(COMPOSE_DEV) down

restart: ## Restart all services
	$(COMPOSE_DEV) restart

logs: ## Follow logs for all services
	$(COMPOSE_DEV) logs -f

logs-backend: ## Follow backend logs only
	$(COMPOSE_DEV) logs -f backend

logs-celery: ## Follow all celery worker logs
	$(COMPOSE_DEV) logs -f celery-worker-market celery-worker-ai celery-worker-default celery-beat

ps: ## Show status of all containers
	$(COMPOSE_DEV) ps

# ---------------------------------------------------------------------------
# Django — Shell & Management
# ---------------------------------------------------------------------------
shell: ## Open Django shell (plus)
	$(BACKEND) python manage.py shell

bash: ## Open bash shell in backend container
	$(BACKEND) bash

migrate: ## Apply database migrations
	$(BACKEND) python manage.py migrate

makemigrations: ## Generate new migration files
	$(BACKEND) python manage.py makemigrations

showmigrations: ## Show migration status for all apps
	$(BACKEND) python manage.py showmigrations

createsuperuser: ## Create a Django admin superuser
	$(BACKEND) python manage.py createsuperuser

collectstatic: ## Collect static files
	$(BACKEND) python manage.py collectstatic --no-input

# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------
test: ## Run the full test suite
	$(BACKEND) pytest

test-fast: ## Run tests without slow integration tests
	$(BACKEND) pytest -m "not integration" --no-header -q

test-cov: ## Run tests with HTML + terminal coverage report
	$(BACKEND) pytest \
		--cov=. \
		--cov-report=html:htmlcov \
		--cov-report=term-missing \
		--cov-fail-under=70

# ---------------------------------------------------------------------------
# Code Quality
# ---------------------------------------------------------------------------
lint: ## Run ruff linter (check only)
	$(BACKEND) ruff check .

format: ## Format code with black and isort
	$(BACKEND) bash -c "black . && isort ."

type-check: ## Run mypy type checker
	$(BACKEND) mypy .

pre-commit-install: ## Install pre-commit hooks into git
	$(BACKEND) pre-commit install

# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------
frontend-install: ## Install frontend npm dependencies
	$(FRONTEND) npm install

frontend-build: ## Build frontend for production
	$(FRONTEND) npm run build

# ---------------------------------------------------------------------------
# Celery Monitoring
# ---------------------------------------------------------------------------
flower: ## Print Flower URL (Celery task monitor — dev only)
	@echo "  Flower (Celery monitor): http://localhost:5555"

# ---------------------------------------------------------------------------
# Setup & Teardown
# ---------------------------------------------------------------------------
setup: ## First-time project setup (copies .env, builds, migrates)
	@bash scripts/bootstrap.sh

backup: ## Back up PostgreSQL and Redis data
	@bash scripts/backup.sh

restore: ## Restore from a backup file (usage: make restore FILE=backups/postgres_xxx.sql.gz)
	@bash scripts/restore.sh $(FILE)

clean: ## Stop containers and remove orphan containers (keeps volumes)
	$(COMPOSE_DEV) down --remove-orphans

nuke: ## ⚠️  Destroy ALL containers, volumes, and data (irreversible)
	@bash scripts/reset.sh