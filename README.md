# Payment Processing

Асинхронный процессинг платежей: API принимает платёж и отвечает `202`, платёж обрабатывается
через эмулятор шлюза, результат приходит клиенту webhook'ом.

FastAPI · SQLAlchemy 2.0 (async) · PostgreSQL · RabbitMQ (FastStream) · Alembic · Docker

## Запуск

Нужны Docker с `docker compose` и `make`.

```bash
cp .env.local .env
make up
```

| | |
|---|---|
| API | http://localhost:8000/api/v1/payments |
| Swagger | http://localhost:8000/api/docs |
| ReDoc | http://localhost:8000/api/redoc |
| OpenAPI (JSON) | http://localhost:8000/api/openapi.json |
| RabbitMQ UI | http://localhost:15672 (`payment` / `payment`) |

Дополнительно: `make monitoring` — Prometheus (:9090) и Grafana (:3000, `admin` / `admin`),
`make nginx` — nginx на :8080. Остановить — `make down`, все команды — `make help`.

## Структура проекта

Одна кодовая база запускается в трёх ролях. Роль задаёт переменная `APISERVICE_APP_TYPE`:

- `api` — HTTP API;
- `producer` — outbox relay;
- `consumer` — обработчик платежей.

```text
main.py                  точка входа: читает APP_TYPE и запускает нужную роль
                         (api перед стартом применяет миграции)
app/
├── api/                 HTTP-слой (FastAPI)
│   ├── v1/payments.py   эндпоинты POST /payments и GET /payments/{id}
│   ├── v1/schemas.py    схемы запросов и ответов API v1
│   ├── v1/deps.py       сборка PaymentService для эндпоинтов
│   ├── deps.py          зависимости: сессия БД, репозитории, проверка X-API-Key
│   ├── handlers.py      перевод доменных исключений в HTTP-ответы
│   ├── health.py        /health
│   └── schemas.py       модели ошибок для OpenAPI
├── consumer/            подписчики RabbitMQ: очередь payments.new → PaymentProcessor
├── core/                инфраструктура
│   ├── config.py        настройки из переменных окружения (pydantic-settings)
│   ├── db.py            движок и сессии SQLAlchemy
│   ├── broker.py        топология RabbitMQ: exchange, очереди, retry, DLQ
│   ├── log.py           настройка логирования
│   └── metrics.py       метрики Prometheus и middleware для HTTP
├── services/            бизнес-логика
│   ├── payment.py       создание платежа с идемпотентностью и запись в outbox
│   ├── processor.py     обработка: шлюз → статус в БД → webhook
│   ├── gateway.py       эмулятор платёжного шлюза
│   ├── webhook.py       отправка webhook клиенту
│   ├── relay.py         outbox relay: публикует события из БД в RabbitMQ
│   ├── publisher.py     маршрутизация событий outbox в RabbitMQ
│   ├── retry.py         повторы с экспоненциальной задержкой и уход в DLQ
│   ├── security.py      проверка API-ключа
│   ├── exceptions.py    доменные исключения
│   └── _dto.py, _schemas.py   DTO между слоями и схема webhook
├── workers/             фабрики приложений для каждой роли
│   ├── server.py        api (FastAPI)
│   ├── producer.py      producer (FastStream + relay)
│   └── consumer.py      consumer (FastStream)
├── models.py            ORM-модели: Payment, Outbox
└── repository.py        доступ к БД: PaymentRepository, OutboxRepository
migrations/              миграции Alembic
infra/                   Dockerfile, docker-compose (local/prod), nginx, Prometheus, Grafana
tests/
├── fixtures/            фикстуры: контейнеры PostgreSQL и RabbitMQ, фейки шлюза и webhook
├── test_00_smoke/       конфигурация, схема БД, топология брокера, OpenAPI
├── test_01_functional/  юнит-тесты сервисов на фейках, без внешних зависимостей
├── test_02_integration/ репозитории и брокер на реальных PostgreSQL и RabbitMQ
└── test_03_e2e/         полный путь: API → outbox → RabbitMQ → consumer → webhook
.github/workflows/       CI (линтеры и тесты) и деплой
```

## Документация

- [DEVELOPMENT.md](DEVELOPMENT.md) — тесты, линтеры, запуск без Docker
- [Swagger UI](http://localhost:8000/api/docs) и [ReDoc](http://localhost:8000/api/redoc) — интерактивная документация API (после `make up`)
- [openapi.json](http://localhost:8000/api/openapi.json) — спецификация OpenAPI
