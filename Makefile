# StyleSense developer commands. Run `make help`.
SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help
MAKEFLAGS += --no-print-directory

BACKEND := backend
UV      := uv --directory $(BACKEND)
COMPOSE := docker compose --env-file .env -f infra/compose/compose.yml
DEV     := $(COMPOSE) -f infra/compose/compose.dev.yml
OBS     := $(DEV) -f infra/compose/compose.observability.yml
VERSION ?= $(shell git describe --tags --always --dirty 2>/dev/null || echo dev)

##@ Setup
.PHONY: setup
setup: ## Install deps, git hooks and create .env
	$(UV) sync --frozen
	$(UV) run pre-commit install --install-hooks -t pre-commit -t commit-msg
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example")

##@ Quality
.PHONY: fmt lint typecheck imports check
fmt: ## Auto-format and fix lint
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

lint: ## Lint and format check (no changes)
	$(UV) run ruff check .
	$(UV) run ruff format --check .

typecheck: ## mypy --strict
	$(UV) run mypy

imports: ## Enforce architecture layers
	$(UV) run lint-imports

check: lint typecheck imports test ## Everything CI runs

##@ Tests
.PHONY: test test-unit test-integration cov
test: ## All tests with coverage gate (needs Docker)
	$(UV) run pytest --cov --cov-report=term-missing --cov-report=xml

test-unit: ## Fast tests, no Docker
	$(UV) run pytest tests/unit

test-integration: ## Real Postgres/Redis via testcontainers
	$(UV) run pytest tests/integration

cov: ## HTML coverage report
	$(UV) run pytest --cov --cov-report=html && echo "open backend/htmlcov/index.html"

##@ Database
.PHONY: migrate migration downgrade
migrate: ## Apply migrations (local DB from .env)
	$(UV) run --env-file ../.env alembic upgrade head

migration: ## New migration: make migration m="add users"
	@test -n "$(m)" || (echo 'usage: make migration m="message"' && exit 1)
	$(UV) run --env-file ../.env alembic revision --autogenerate -m "$(m)"

downgrade: ## Roll back one migration
	$(UV) run --env-file ../.env alembic downgrade -1

##@ Data
.PHONY: seed
seed: ## Load the mock catalog + embeddings into the dev stack (refuses production)
	$(DEV) exec api python -m stylesense.cli seed-catalog

##@ Run
.PHONY: up down logs ps build run shell-db
up: ## Start dev stack (postgres, redis, api with reload)
	APP_VERSION=$(VERSION) $(DEV) up -d --build

down: ## Stop dev stack (keeps data)
	$(DEV) down

logs: ## Tail logs: make logs s=api
	$(DEV) logs -f $(s)

ps: ## Service status
	$(DEV) ps

build: ## Build production image
	docker build --target runtime --build-arg VERSION=$(VERSION) -t stylesense-api:$(VERSION) $(BACKEND)

run: ## Run API on the host against the dev stack's DB/Redis
	$(UV) run --env-file ../.env uvicorn stylesense.main:create_app --factory --reload

shell-db: ## psql into the dev database
	$(DEV) exec postgres sh -c 'psql -U $$POSTGRES_USER -d $$POSTGRES_DB'

##@ Observability
.PHONY: obs-up obs-down obs-ps
obs-up: ## Dev stack + Grafana/Prometheus/Tempo/GlitchTip/Uptime Kuma
	APP_VERSION=$(VERSION) $(OBS) up -d --build
	@echo "Grafana http://localhost:3001  Prometheus http://localhost:9090  GlitchTip http://localhost:8001  Uptime Kuma http://localhost:3002"

obs-down: ## Stop everything including observability (keeps data)
	$(OBS) down

obs-ps: ## Status of all services
	$(OBS) ps

##@ Housekeeping
.PHONY: clean nuke help
clean: ## Remove caches and build artifacts
	find $(BACKEND) -type d \( -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache -o -name .ruff_cache -o -name htmlcov \) -prune -exec rm -rf {} +
	rm -f $(BACKEND)/.coverage $(BACKEND)/coverage.xml

nuke: ## Stop stack AND delete volumes (destroys local data)
	@read -p "Delete all local data (DB, Redis, metrics, traces, errors)? [y/N] " ans && [ "$$ans" = y ]
	$(OBS) down -v

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage: make \033[36m<target>\033[0m\n"} \
	/^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2 } \
	/^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) }' $(MAKEFILE_LIST)
