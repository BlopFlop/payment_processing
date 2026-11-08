import asyncio

import uvicorn

from alembic.command import upgrade
from alembic.config import Config
from prometheus_client import start_http_server

from app.core.config import AppType, Settings
from app.core.log import configure_logging


if __name__ == "__main__":
    settings = Settings()

    configure_logging(level=settings.LOG_LEVEL, log_file=settings.LOG_FILE)

    if settings.APP_TYPE == AppType.API:
        config = Config("alembic.ini")
        upgrade(config, "head")

        from app.workers import init_api

        app = init_api()
        uvicorn.run(
            app,
            host=settings.HOST,
            port=settings.PORT,
            log_config=None,
            proxy_headers=True,
            forwarded_allow_ips="*",
        )

    elif settings.APP_TYPE == AppType.PRODUCER:
        from app.workers import init_producer

        start_http_server(settings.METRICS_PORT)
        producer = init_producer()
        asyncio.run(producer.run())

    elif settings.APP_TYPE == AppType.CONSUMER:
        from app.workers import init_consumer

        start_http_server(settings.METRICS_PORT)
        consumer = init_consumer()
        asyncio.run(consumer.run())
