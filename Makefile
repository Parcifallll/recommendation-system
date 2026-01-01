PROJECT_NAME := recommendation-system
DOCKER_COMPOSE := docker-compose
PYTHON := python3
INFRA_SERVICES := postgres redis

RED := \033[0;31m
GREEN := \033[0;32m
BLUE := \033[0;34m
NC := \033[0m

.PHONY: help dev infra infra-up infra-down run logs clean clean-all \
        status ps db-connect alembic-upgrade alembic-downgrade

help:
	@echo "$(GREEN)Available commands:$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	   awk 'BEGIN {FS = ":.*?## "}; {printf "$(BLUE)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""

debug:
	python -m main
dev: run ## build and run app + infrastructure

infra: infra-up
infra-up: ## run infrastructure
	@$(DOCKER_COMPOSE) up --detach $(INFRA_SERVICES)

infra-down: ## stop infrastructure
	@$(DOCKER_COMPOSE) stop $(INFRA_SERVICES)

infra-logs: ## show infrastructure logs
	@$(DOCKER_COMPOSE) logs --follow $(INFRA_SERVICES)

run: infra-up ## run app + infrastructure
	@$(DOCKER_COMPOSE) up --build app

run-detached: infra-up ## run app without logs
	@$(DOCKER_COMPOSE) up --build --detach app

app-logs: ## show app logs
	@$(DOCKER_COMPOSE) logs --follow app

app-stop: ## stop app
	@$(DOCKER_COMPOSE) stop app

app-restart: app-stop run ## restart app


redis-connect:
	@docker exec -it rec-sys-redis redis-cli -a dev_redis
db-connect: ## connect to PostgreSQL
	@$(DOCKER_COMPOSE) exec postgres psql --username $$(grep POSTGRES_USER .env | cut --delimiter='=' --fields=2) --dbname $$(grep POSTGRES_DB .env | cut --delimiter='=' --fields=2)

alembic-upgrade: ## run migrations
	@$(DOCKER_COMPOSE) exec app alembic upgrade head

alembic-downgrade: ## rollback migrations
	@$(DOCKER_COMPOSE) exec app alembic downgrade -1

alembic-history: ## migration history
	@$(DOCKER_COMPOSE) exec app alembic history

status: ## services status
	@docker ps

ps: status

logs: ## show logs
	@$(DOCKER_COMPOSE) logs --follow

clean: ## stop containers
	@$(DOCKER_COMPOSE) down

clean-all: ## full cleanup (volumes and images)
	@$(DOCKER_COMPOSE) down --volumes --remove-orphans
	@docker image prune --force