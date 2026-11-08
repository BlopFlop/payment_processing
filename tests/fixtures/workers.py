from collections.abc import AsyncIterator
from functools import partial
from types import SimpleNamespace

import httpx

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import pytest

from faststream import FastStream
from faststream.rabbit import RabbitBroker, RabbitQueue
from testcontainers.core.container import DockerContainer

from tests.fixtures.fakes import FakeGateway, FakeWebhookServer


@pytest.fixture(scope="session")
async def e2e_clean_state(
    init_db: None,
    local_sessionmaker: async_sessionmaker[AsyncSession],
    broker: RabbitBroker,
    all_queues: list[RabbitQueue],
) -> None:
    async with local_sessionmaker() as session:
        await session.execute(text("TRUNCATE payments, outbox RESTART IDENTITY"))
        await session.commit()

    for queue in all_queues:
        await (await broker.declare_queue(queue)).purge()


@pytest.fixture(scope="session")
async def producer_app(e2e_clean_state: None, rabbit_container: DockerContainer) -> AsyncIterator[FastStream]:
    from app.workers import producer as producer_module

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("APISERVICE_APP_TYPE", "producer")
        app = producer_module.init_app()
        await app.start()

    yield app

    await app.stop()


@pytest.fixture(scope="session")
async def consumer_app(
    e2e_clean_state: None,
    rabbit_container: DockerContainer,
    fake_gateway: FakeGateway,
    webhook_server: FakeWebhookServer,
) -> AsyncIterator[FastStream]:
    from app.workers import consumer as consumer_module

    transport = httpx.MockTransport(webhook_server.handler)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("APISERVICE_APP_TYPE", "consumer")
        monkeypatch.setattr(consumer_module, "GatewayMock", lambda: fake_gateway)
        monkeypatch.setattr(
            consumer_module,
            "httpx",
            SimpleNamespace(AsyncClient=partial(httpx.AsyncClient, transport=transport)),
        )
        app = consumer_module.init_app()
        await app.start()

    yield app

    await app.stop()


@pytest.fixture(scope="session")
async def e2e_stack(app: FastAPI, producer_app: FastStream, consumer_app: FastStream) -> None:
    return
