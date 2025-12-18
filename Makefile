.PHONY: install run test seed clean docker-up docker-down help

help:  ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install:  ## Install dependencies
	pip install -r requirements.txt

docker-up:  ## Start PostgreSQL and Redis
	docker-compose up -d
	@echo "Waiting for services to be ready..."
	@sleep 5

docker-down:  ## Stop PostgreSQL and Redis
	docker-compose down

docker-clean:  ## Stop and remove volumes
	docker-compose down -v

seed:  ## Seed database with test data
	python seed_data.py

run:  ## Run the application
	python -m app.main

dev:  ## Run in development mode with reload
	uvicorn app.main:app --reload --port 8000

test:  ## Run API tests
	python test_api.py

clean:  ## Clean cache files
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} +

setup: docker-up seed  ## Full setup (Docker + seed data)
	@echo "✅ Setup complete! Run 'make run' to start the service"

all: install setup run  ## Install, setup and run
