.PHONY: dev down init-db migrate api web test test-unit test-cov test-e2e test-integration test-all load-test lint format build clean logs shell setup help

COMPOSE := docker compose
BACKEND := backend
FRONTEND := frontend

## ── Development ─────────────────────────────────────────────

setup: ## First-time developer setup (prereqs, deps, services, DB)
	bash infra/scripts/dev-setup.sh

dev: ## Start all services in background
	$(COMPOSE) up -d

down: ## Stop all services
	$(COMPOSE) down

build: ## Build all Docker images
	$(COMPOSE) build

clean: ## Stop all services and remove volumes
	$(COMPOSE) down -v

logs: ## Tail logs from all services
	$(COMPOSE) logs -f

shell: ## Open a shell in the API container
	$(COMPOSE) exec rayolly-api bash

## ── Database ────────────────────────────────────────────────

init-db: ## Run ClickHouse schema migrations
	@echo "Running ClickHouse migrations..."
	@for f in $(BACKEND)/migrations/clickhouse/*.sql; do \
		echo "  → $$(basename $$f)"; \
		$(COMPOSE) exec -T clickhouse clickhouse-client \
			--user rayolly --password rayolly_dev \
			--multiquery < "$$f" 2>/dev/null || true; \
	done
	@echo "Done."

migrate: ## Run PostgreSQL (Alembic) migrations
	cd $(BACKEND) && alembic upgrade head

seed: ## Seed demo data into ClickHouse
	cd $(BACKEND) && python scripts/seed_demo_data.py

## ── Local (no Docker) ───────────────────────────────────────

api: ## Run backend API server locally
	cd $(BACKEND) && uvicorn rayolly.api.app:app \
		--host 0.0.0.0 \
		--port 8080 \
		--reload \
		--loop uvloop \
		--log-level debug

web: ## Run frontend dev server locally
	cd $(FRONTEND) && npm run dev

## ── Quality ─────────────────────────────────────────────────

test: ## Run all backend tests
	cd $(BACKEND) && python -m pytest tests/ -v --tb=short

test-unit: ## Run unit tests only
	cd $(BACKEND) && python -m pytest tests/unit/ -v --tb=short

test-cov: ## Run tests with coverage report
	cd $(BACKEND) && python -m pytest tests/ -v --tb=short \
		--cov=rayolly --cov-report=term-missing --cov-report=html

test-e2e: ## Run end-to-end tests
	cd $(BACKEND) && python -m pytest tests/e2e/ -v --tb=short

test-integration: ## Run integration tests (requires make dev)
	cd $(BACKEND) && python -m pytest tests/integration/ -v --tb=short -m integration

test-all: ## Run all tests
	cd $(BACKEND) && python -m pytest tests/ -v --tb=short

load-test: ## Run load test (requires locust: pip install locust)
	cd $(BACKEND) && locust -f tests/load/locustfile.py --host=http://localhost:8080

lint: ## Run linters (ruff + mypy)
	cd $(BACKEND) && ruff check . && mypy rayolly/ --ignore-missing-imports

format: ## Auto-format code
	cd $(BACKEND) && ruff format .

## ── Frontend ────────────────────────────────────────────────

web-lint: ## Lint frontend
	cd $(FRONTEND) && npm run lint

web-types: ## Type-check frontend
	cd $(FRONTEND) && npm run type-check

web-build: ## Build frontend for production
	cd $(FRONTEND) && npm run build

## ── Help ────────────────────────────────────────────────────

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
