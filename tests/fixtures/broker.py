import json
import asyncio

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

import pytest

from aio_pika import IncomingMessage
from faststream.rabbit import RabbitBroker, RabbitQueue
from testcontainers.core.container import DockerContainer

from app.core.broker import PAYMENTS_DLQ, PAYMENTS_NEW_QUEUE, build_retry_queues, declare_topology, init_broker
from app.core.config import BrokerSettings


@dataclass
class ReceivedMessage:
    body: dict[str, Any]
    headers: dict[str, Any]
    message_id: str | None
    delivery_mode: int | None

    @classmethod
    def from_incoming(cls, message: IncomingMessage) -> "ReceivedMessage":
        return cls(
            body=json.loads(message.body),
            headers=dict(message.headers or {}),
            message_id=message.message_id,
            delivery_mode=int(message.delivery_mode) if message.delivery_mode else None,
        )


class FetchMessage(Protocol):
    async def __call__(self, queue: RabbitQueue, timeout: float = 5.0) -> ReceivedMessage | None: ...


FetchAllMessages = Callable[[RabbitQueue], Awaitable[list[ReceivedMessage]]]


@pytest.fixture(scope="session")
def broker_settings(rabbit_container: DockerContainer) -> BrokerSettings:
    return BrokerSettings()


@pytest.fixture(scope="session")
def retry_queues(broker_settings: BrokerSettings) -> list[RabbitQueue]:
    return build_retry_queues(broker_settings.RETRY_MAX_ATTEMPTS, broker_settings.RETRY_BASE_DELAY)


@pytest.fixture(scope="session")
async def broker(broker_settings: BrokerSettings, retry_queues: list[RabbitQueue]) -> AsyncIterator[RabbitBroker]:
    broker = init_broker(broker_settings)
    await broker.connect()
    await declare_topology(broker, retry_queues)

    yield broker

    await broker.stop()


@pytest.fixture(scope="session")
def all_queues(retry_queues: list[RabbitQueue]) -> list[RabbitQueue]:
    return [PAYMENTS_NEW_QUEUE, PAYMENTS_DLQ, *retry_queues]


@pytest.fixture(scope="function")
async def purge_queues(broker: RabbitBroker, all_queues: list[RabbitQueue]) -> None:
    for queue in all_queues:
        await (await broker.declare_queue(queue)).purge()


@pytest.fixture(scope="session")
def fetch_message(broker: RabbitBroker) -> FetchMessage:

    async def func(queue: RabbitQueue, timeout: float = 5.0) -> ReceivedMessage | None:
        aio_queue = await broker.declare_queue(queue)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            message = await aio_queue.get(no_ack=False, fail=False)
            if message is not None:
                await message.ack()
                return ReceivedMessage.from_incoming(message)
            if loop.time() > deadline:
                return None
            await asyncio.sleep(0.05)

    return func


@pytest.fixture(scope="session")
def fetch_all_messages(broker: RabbitBroker) -> FetchAllMessages:

    async def func(queue: RabbitQueue) -> list[ReceivedMessage]:
        aio_queue = await broker.declare_queue(queue)
        result = []
        while (message := await aio_queue.get(no_ack=False, fail=False)) is not None:
            await message.ack()
            result.append(ReceivedMessage.from_incoming(message))
        return result

    return func
