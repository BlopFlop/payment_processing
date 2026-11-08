import logging

from functools import partial

import httpx

from faststream import ContextRepo, FastStream

from ._db import check_db
from app.consumer import get_subscribers
from app.core.broker import FASTSTREAM_LOGGER, build_retry_queues, declare_topology, init_broker
from app.core.config import Settings
from app.core.db import create_session, get_async_sessionmaker
from app.core.log import configure_logging
from app.services.gateway import GatewayMock
from app.services.processor import PaymentProcessor
from app.services.retry import Retry
from app.services.webhook import HttpWebhookSender


logger = logging.getLogger(__name__)


async def on_startup(context: ContextRepo) -> None:
    settings: Settings = context.get("settings")

    await check_db(settings.database)


async def after_startup(context: ContextRepo) -> None:
    settings: Settings = context.get("settings")
    broker = context.get("broker")

    retry_queues = build_retry_queues(
        max_attempts=settings.broker.RETRY_MAX_ATTEMPTS, base_delay=settings.broker.RETRY_BASE_DELAY
    )
    await declare_topology(broker, retry_queues)

    sessionmaker = get_async_sessionmaker(settings.database, application_name=settings.broker.OUTBOX_APP_NAME)
    session_factory = partial(create_session, sessionmaker)

    client = httpx.AsyncClient(timeout=settings.broker.WEBHOOK_TIMEOUT)

    context.set_global("client", client)

    processor = PaymentProcessor(
        session_factory=session_factory,
        gateway=GatewayMock(),
        webhook=HttpWebhookSender(client),
    )
    context.set_global("processor", processor)
    context.set_global("retry", Retry(broker, retry_queues))


async def on_shutdown(context: ContextRepo) -> None:
    client: httpx.AsyncClient = context.get("client")
    await client.aclose()


def init_app() -> FastStream:
    settings = Settings()
    configure_logging(level=settings.LOG_LEVEL, log_file=settings.LOG_FILE)
    broker = init_broker(settings.broker, app_name=settings.APP_TYPE.value)

    app = FastStream(broker, logger=FASTSTREAM_LOGGER)
    app.context.set_global("settings", settings)
    app.context.set_global("broker", broker)

    app.on_startup(on_startup)
    app.on_shutdown(on_shutdown)
    app.after_startup(after_startup)

    get_subscribers(broker)

    return app
