from collections.abc import AsyncIterator, Iterator
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from os import environ
from pathlib import Path


environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import pytest

from testcontainers.community.postgres import PostgresContainer
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import LogMessageWaitStrategy

from app.core.db import create_session


pytest.register_assert_rewrite("tests.fixtures")

from tests.fixtures.database import SessionFactory  # noqa: E402


pytest_plugins = [
    "tests.fixtures.database",
    "tests.fixtures.payments",
    "tests.fixtures.broker",
    "tests.fixtures.fakes",
    "tests.fixtures.workers",
]

TESTS_FOLDER = Path(__file__).parent.resolve()
PROJECT_FOLDER = TESTS_FOLDER.parent.resolve()

API_KEY = "test-api-key"
RABBITMQ_USER = "test"
RABBITMQ_PASSWORD = "test"


@pytest.fixture(scope="session")
def api_key() -> str:
    return API_KEY


@pytest.fixture(scope="session", autouse=True)
def base_settings(api_key: str) -> Iterator[None]:
    monkeypatch = pytest.MonkeyPatch()

    monkeypatch.setenv("APISERVICE_APP_TYPE", "api")
    monkeypatch.setenv("APISERVICE_API_KEY", api_key)
    monkeypatch.setenv("APISERVICE_LOG_LEVEL", "DEBUG")

    monkeypatch.setenv("POSTGRES_DB", "test")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setenv("POSTGRES_USER", "test")

    monkeypatch.setenv("BROKERSERVICE_URL", f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASSWORD}@localhost:5672/")
    monkeypatch.setenv("BROKERSERVICE_RETRY_BASE_DELAY", "0.1")
    monkeypatch.setenv("BROKERSERVICE_OUTBOX_POLL_INTERVAL", "0.1")
    monkeypatch.setenv("BROKERSERVICE_WEBHOOK_TIMEOUT", "2")

    yield

    monkeypatch.undo()


@pytest.fixture(scope="session")
def db_container() -> Iterator[PostgresContainer]:
    with PostgresContainer(
        image="postgres:17-alpine",
        username="test",
        password="testing",
        dbname="payment_test",
        driver="asyncpg",
    ) as container:
        environ["POSTGRES_HOST"] = container.get_container_host_ip()
        environ["POSTGRES_USER"] = container.username
        environ["POSTGRES_PASSWORD"] = container.password
        environ["POSTGRES_PORT"] = str(container.get_exposed_port(5432))
        environ["POSTGRES_DB"] = container.dbname

        yield container


@pytest.fixture(scope="session")
def rabbit_container() -> Iterator[DockerContainer]:
    container = (
        DockerContainer("rabbitmq:3.13-alpine")
        .with_env("RABBITMQ_DEFAULT_USER", RABBITMQ_USER)
        .with_env("RABBITMQ_DEFAULT_PASS", RABBITMQ_PASSWORD)
        .with_exposed_ports(5672)
        .waiting_for(LogMessageWaitStrategy("Server startup complete").with_startup_timeout(120))
    )
    with container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(5672)
        environ["BROKERSERVICE_URL"] = f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASSWORD}@{host}:{port}/"

        yield container


@pytest.fixture(scope="session")
def init_db(db_container: PostgresContainer) -> None:
    from alembic import command, config

    alembic_cfg = config.Config(str(PROJECT_FOLDER / "alembic.ini"))
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(command.upgrade, alembic_cfg, "head").result()


@pytest.fixture(scope="session")
def db_url(init_db: None, db_container: PostgresContainer) -> str:
    return db_container.get_connection_url()


@pytest.fixture(scope="session")
async def engine(db_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(db_url)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
def local_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        autoflush=False,
        expire_on_commit=False,
    )


@pytest.fixture(scope="session")
def session_factory(local_sessionmaker: async_sessionmaker[AsyncSession]) -> SessionFactory:
    return partial(create_session, local_sessionmaker)


@pytest.fixture(scope="function")
async def session(local_sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with local_sessionmaker() as session, session.begin():
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@pytest.fixture(scope="session")
async def app(init_db: None) -> AsyncIterator[FastAPI]:
    from app.workers import init_api
    from app.workers.server import lifespan

    app = init_api()

    async with lifespan(app):
        yield app


@pytest.fixture(scope="session")
async def client(app: FastAPI, api_key: str) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app),
        base_url="http://testserver/api",
        headers={"X-API-Key": api_key},
    ) as client:
        yield client


@pytest.fixture(scope="session")
async def anon_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app),
        base_url="http://testserver/api",
    ) as client:
        yield client
