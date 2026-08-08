# TaskFlow ERP — common developer + ops commands.
# Usage: `make <target>`. On Windows, run under Git Bash or WSL.

.DEFAULT_GOAL := help
COMPOSE := docker compose

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---- Docker stack ----------------------------------------------------------
.PHONY: up
up: ## Build + start the full stack (db, redis, api, worker, beat, web)
	$(COMPOSE) up --build -d

.PHONY: down
down: ## Stop the stack
	$(COMPOSE) down

.PHONY: logs
logs: ## Tail all service logs
	$(COMPOSE) logs -f

.PHONY: ps
ps: ## Show running services
	$(COMPOSE) ps

.PHONY: observability
observability: ## Start Prometheus + Grafana alongside the stack
	$(COMPOSE) --profile observability up --build -d

# ---- Backend ---------------------------------------------------------------
.PHONY: migrate
migrate: ## Run DB migrations in the api container
	$(COMPOSE) exec api python manage.py migrate

.PHONY: seed
seed: ## Load demo data
	$(COMPOSE) exec api python manage.py seed_demo

.PHONY: superuser
superuser: ## Create a Django superuser
	$(COMPOSE) exec api python manage.py createsuperuser

.PHONY: shell
shell: ## Django shell in the api container
	$(COMPOSE) exec api python manage.py shell

# ---- Quality ---------------------------------------------------------------
.PHONY: lint
lint: ## Ruff lint the backend
	cd django-backend && ruff check .

.PHONY: test
test: ## Run backend tests
	cd django-backend && pytest

.PHONY: typecheck
typecheck: ## Typecheck the frontend
	cd react-frontend && npm run typecheck
