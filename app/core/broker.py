import logging

from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue
from faststream.rabbit.prometheus import RabbitPrometheusMiddleware
from faststream.rabbit.schemas import Channel
from prometheus_client import REGISTRY

from app.core.config import BrokerSettings


FASTSTREAM_LOGGER = logging.getLogger("app.faststream")


def init_broker(settings: BrokerSettings, app_name: str = "payment") -> RabbitBroker:
    return RabbitBroker(
        settings.URL.get_secret_value(),
        default_channel=Channel(
            prefetch_count=settings.CONSUMER_PREFETCH,
            publisher_confirms=True,
            on_return_raises=True,
        ),
        middlewares=[RabbitPrometheusMiddleware(registry=REGISTRY, app_name=app_name)],
        logger=FASTSTREAM_LOGGER,
    )


ATTEMPT_HEADER = "x-attempt"
ERROR_HEADER = "x-last-error"

NEW_ROUTING_KEY = "payments.new"
DLQ_ROUTING_KEY = "payments.dlq"

PAYMENTS_EXCHANGE = RabbitExchange("payments", type=ExchangeType.DIRECT, durable=True)
DLX_EXCHANGE = RabbitExchange("payments.dlx", type=ExchangeType.DIRECT, durable=True)

PAYMENTS_NEW_QUEUE = RabbitQueue(
    "payments.new",
    durable=True,
    routing_key=NEW_ROUTING_KEY,
    arguments={
        "x-dead-letter-exchange": DLX_EXCHANGE.name,
        "x-dead-letter-routing-key": DLQ_ROUTING_KEY,
    },
)

PAYMENTS_DLQ = RabbitQueue("payments.dlq", durable=True, routing_key=DLQ_ROUTING_KEY)


def build_retry_queues(max_attempts: int, base_delay: float) -> list[RabbitQueue]:
    return [
        RabbitQueue(
            f"payments.retry.{attempt}",
            durable=True,
            arguments={
                "x-message-ttl": int(base_delay * 1000 * 2**attempt),
                "x-dead-letter-exchange": PAYMENTS_EXCHANGE.name,
                "x-dead-letter-routing-key": NEW_ROUTING_KEY,
            },
        )
        for attempt in range(max(max_attempts - 1, 0))
    ]


async def declare_topology(broker: RabbitBroker, retry_queues: list[RabbitQueue]) -> None:
    payments_exchange = await broker.declare_exchange(PAYMENTS_EXCHANGE)
    dlx = await broker.declare_exchange(DLX_EXCHANGE)

    new_queue = await broker.declare_queue(PAYMENTS_NEW_QUEUE)
    await new_queue.bind(payments_exchange, routing_key=NEW_ROUTING_KEY)

    dlq = await broker.declare_queue(PAYMENTS_DLQ)
    await dlq.bind(dlx, routing_key=DLQ_ROUTING_KEY)

    for queue in retry_queues:
        await broker.declare_queue(queue)
