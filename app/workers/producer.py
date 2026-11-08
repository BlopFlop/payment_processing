import asyncio
import logging

from contextlib import suppress
from functools import partial

from faststream import ContextRepo, FastStream

from ._db import check_db
from app.core.broker import FASTSTREAM_LOGGER, build_retry_queues, declare_topology, init_broker
from app.core.config import Settings
from app.core.db import create_session, get_async_sessionmaker
from app.core.log import configure_logging
from app.services.publisher import Publisher
from app.services.relay import RelayService


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

    publisher = Publisher(broker)
    relay_service = RelayService(
        publisher=publisher,
        session_factory=session_factory,
        batch_size=settings.broker.OUTBOX_BATCH_SIZE,
        interval=settings.broker.OUTBOX_POLL_INTERVAL,
    )
    task = asyncio.create_task(relay_service.start(), name="outbox-relay")
    context.set_global("relay_task", task)
    context.set_global("relay_service", relay_service)


async def on_shutdown(context: ContextRepo) -> None:
    relay_service: RelayService = context.get("relay_service")
    relay_service.stop()

    task: asyncio.Task[None] | None = context.get("relay_task")

    if task is not None and not task.done():
        try:
            await asyncio.wait_for(task, timeout=30)
        except TimeoutError:
            logger.warning("Relay не остановился, отменяем")
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


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

    return app
