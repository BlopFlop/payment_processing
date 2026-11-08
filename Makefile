ENV_FILE ?= .env
export ENV_FILE
COMPOSE := docker compose -f infra/docker-compose.local.yaml --env-file $(ENV_FILE)
COMPOSE_PROD := docker compose -f infra/docker-compose.prod.yaml --env-file $(ENV_FILE)

.PHONY: help build up down down-v ps logs monitoring nginx prod-config test lint format typecheck

help:  ## список команд
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

build:  ## собрать образ приложения
	$(COMPOSE) build

up:  ## поднять приложение (postgres, rabbitmq, migrate, api, producer, consumer)
	$(COMPOSE) up -d --build

monitoring:  ## приложение + Prometheus и Grafana
	$(COMPOSE) --profile monitoring up -d --build

nginx:  ## приложение + nginx на :8080
	$(COMPOSE) --profile nginx up -d --build

down:  ## остановить всё (данные сохраняются)
	$(COMPOSE) --profile monitoring --profile nginx down

down-v:  ## остановить всё и удалить данные
	$(COMPOSE) --profile monitoring --profile nginx down -v

ps:  ## состояние сервисов
	$(COMPOSE) --profile monitoring --profile nginx ps

logs:  ## логи сервисов (make logs s=consumer)
	$(COMPOSE) logs -f $(s)

prod-config:  ## проверить prod-compose (make prod-config ENV_FILE=.env.prod APP_IMAGE=...)
	$(COMPOSE_PROD) config --quiet && echo "prod compose OK"

test:  ## все тесты (нужен Docker)
	uv run pytest

lint:  ## ruff check + format --check
	uv run ruff check && uv run ruff format --check

format:  ## автоисправление ruff
	uv run ruff check --fix && uv run ruff format

typecheck:  ## mypy (strict)
	uv run mypy
