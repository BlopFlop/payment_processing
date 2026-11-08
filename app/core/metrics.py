import time

from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    Counter,
    Histogram,
    generate_latest,
)


HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Количество HTTP-запросов",
    ["method", "path", "status"],
)
HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "Длительность обработки HTTP-запроса",
    ["method", "path"],
)

PAYMENTS_CREATED = Counter(
    "payments_created_total",
    "Созданные платежи (без учёта повторов по Idempotency-Key)",
    ["currency"],
)
PAYMENTS_IDEMPOTENCY = Counter(
    "payments_idempotency_total",
    "Повторные запросы с занятым Idempotency-Key",
    ["result"],
)
PAYMENTS_PROCESSED = Counter(
    "payments_processed_total",
    "Платежи, финализированные consumer'ом",
    ["status"],
)
GATEWAY_DURATION = Histogram(
    "payment_gateway_duration_seconds",
    "Длительность вызова платёжного шлюза",
    buckets=(0.5, 1, 2, 3, 4, 5, 7.5, 10),
)
WEBHOOK_DELIVERIES = Counter(
    "webhook_deliveries_total",
    "Попытки доставки webhook",
    ["result"],
)
MESSAGE_RETRIES = Counter(
    "payment_messages_retried_total",
    "Сообщения, отправленные на повтор или в DLQ",
    ["target"],
)
OUTBOX_EVENTS = Counter(
    "outbox_events_total",
    "Результаты публикации событий outbox",
    ["result"],
)


class PrometheusMiddleware:
    def __init__(self, app: ASGIApp, exclude: tuple[str, ...] = ("/metrics",)):
        self.app = app
        self.exclude = exclude

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in self.exclude:
            await self.app(scope, receive, send)
            return

        status_code = 500
        started = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            route = scope.get("route")
            path = getattr(route, "path", None) or "unmatched"
            method = scope["method"]
            HTTP_REQUESTS.labels(method, path, str(status_code)).inc()
            HTTP_REQUEST_DURATION.labels(method, path).observe(time.perf_counter() - started)


async def metrics_endpoint(_: Request) -> Response:
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
