# Разработка

## Зависимости

Тесты и линтеры — опциональные зависимости (`[project.optional-dependencies]`), в Docker-образ не попадают.

```bash
uv sync --all-extras
uv run pre-commit install
```

## Тесты

Нужен только запущенный Docker: PostgreSQL и RabbitMQ поднимаются через testcontainers на случайных портах
и не конфликтуют с окружением из `make up`.

```bash
uv run pytest
uv run pytest tests/test_01_functional
make cov
```

`make cov` запускает тесты с замером покрытия кода `app/`: отчёт выводится в терминал, HTML-версия
сохраняется в `htmlcov/index.html`. Если покрытие ниже 90%, команда завершается ошибкой. В CI покрытие
проверяется так же, а итоговая таблица выводится в summary запуска.

| Папка | Что проверяет |
|---|---|
| `tests/test_00_smoke` | всё, что нужно для запуска: конфиг, фабрики приложений, миграции, топология брокера, API |
| `tests/test_01_functional` | логика сервисов на фейках, сценарии через `parametrize` |
| `tests/test_02_integration` | работа с реальными Postgres и RabbitMQ: транзакции, блокировки, retry/DLQ |
| `tests/test_03_e2e` | полные положительные и отрицательные пути через всю систему |

## Линтеры

```bash
uv run ruff check --fix && uv run ruff format
uv run mypy
uv run pre-commit run --all-files
```

## Запуск без Docker

```bash
make up
docker compose -f infra/docker-compose.local.yaml --env-file .env up -d database rabbitmq

uv run alembic upgrade head
APISERVICE_APP_TYPE=api      uv run python main.py
APISERVICE_APP_TYPE=producer uv run python main.py
APISERVICE_APP_TYPE=consumer uv run python main.py
```

Логи: INFO и выше — в консоль, всё — в `logs/<api|producer|consumer>.log`.
