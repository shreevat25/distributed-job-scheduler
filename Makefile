# Distributed Job Scheduler — developer commands. Run `make help` for a list.

SHELL := /bin/bash

BACKEND     := backend
PYTHON      ?= python3.12
VENV        ?= $(BACKEND)/.venv
PY          := $(abspath $(VENV))/bin/python
COMPOSE     ?= docker compose

# Disposable PostgreSQL for the test suite (matches tests/conftest.py defaults).
TEST_DB_CONTAINER ?= djs-test-db
TEST_DB_PORT      ?= 54321
TEST_DATABASE_URL ?= postgresql+asyncpg://djs_user:djs_password@127.0.0.1:$(TEST_DB_PORT)/djs_test_db

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ---------------------------------------------------------------- setup

$(PY):
	$(PYTHON) -m venv $(VENV)

.PHONY: install
install: $(PY) ## Create backend/.venv and install the backend with dev extras
	cd $(BACKEND) && $(PY) -m pip install -e ".[dev]"

# ---------------------------------------------------------------- tests

.PHONY: test-db
test-db: ## Start a disposable PostgreSQL 16 for tests on port 54321
	@docker start $(TEST_DB_CONTAINER) >/dev/null 2>&1 || docker run -d --name $(TEST_DB_CONTAINER) \
		-e POSTGRES_USER=djs_user -e POSTGRES_PASSWORD=djs_password -e POSTGRES_DB=djs_test_db \
		-p $(TEST_DB_PORT):5432 postgres:16-alpine >/dev/null
	@until docker exec $(TEST_DB_CONTAINER) pg_isready -U djs_user -d djs_test_db >/dev/null 2>&1; do sleep 1; done
	@echo "Test database ready at $(TEST_DATABASE_URL)"

.PHONY: test-db-stop
test-db-stop: ## Remove the disposable test database container
	-docker rm -f $(TEST_DB_CONTAINER)

.PHONY: test
test: ## Run the full backend test suite (needs `make test-db` or TEST_DATABASE_URL)
	cd $(BACKEND) && DATABASE_URL=$(TEST_DATABASE_URL) $(PY) -m pytest

.PHONY: test-unit
test-unit: ## Run unit tests only
	cd $(BACKEND) && DATABASE_URL=$(TEST_DATABASE_URL) $(PY) -m pytest tests/unit

.PHONY: test-integration
test-integration: ## Run integration tests only
	cd $(BACKEND) && DATABASE_URL=$(TEST_DATABASE_URL) $(PY) -m pytest tests/integration

# ---------------------------------------------------------------- migrations
# Target database comes from DATABASE_URL (falls back to alembic.ini).

.PHONY: migrate
migrate: ## Apply all migrations (alembic upgrade head)
	cd $(BACKEND) && $(PY) -m alembic upgrade head

.PHONY: migrate-down
migrate-down: ## Roll back the most recent migration
	cd $(BACKEND) && $(PY) -m alembic downgrade -1

.PHONY: migration
migration: ## Autogenerate a migration: make migration msg="add foo column"
	@test -n "$(msg)" || (echo 'usage: make migration msg="describe the change"' && exit 1)
	cd $(BACKEND) && $(PY) -m alembic revision --autogenerate -m "$(msg)"

.PHONY: migrate-check
migrate-check: ## Fail if models have drifted from the migrations
	cd $(BACKEND) && $(PY) -m alembic check

.PHONY: migrate-history
migrate-history: ## Show migration history
	cd $(BACKEND) && $(PY) -m alembic history --verbose

# ---------------------------------------------------------------- run locally

.PHONY: run-api
run-api: ## Run the API with auto-reload on :8000
	cd $(BACKEND) && $(PY) -m uvicorn app.main:app --reload --port 8000

.PHONY: run-worker
run-worker: ## Run a worker process
	cd $(BACKEND) && $(PY) run_worker.py

.PHONY: run-scheduler
run-scheduler: ## Run the promotion/cron scheduler process
	cd $(BACKEND) && $(PY) run_scheduler.py

.PHONY: run-reaper
run-reaper: ## Run the crash-recovery reaper process
	cd $(BACKEND) && $(PY) run_reaper.py

# ---------------------------------------------------------------- docker compose

.PHONY: up
up: ## Build and start the full stack in the background
	$(COMPOSE) up --build -d

.PHONY: down
down: ## Stop the full stack
	$(COMPOSE) down

.PHONY: logs
logs: ## Follow logs from the full stack
	$(COMPOSE) logs -f

.PHONY: ps
ps: ## List stack containers
	$(COMPOSE) ps

# ---------------------------------------------------------------- housekeeping

.PHONY: clean
clean: ## Remove Python caches
	find $(BACKEND) -type d \( -name __pycache__ -o -name .pytest_cache \) -prune -exec rm -rf {} +
