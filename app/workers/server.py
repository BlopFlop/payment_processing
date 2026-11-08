from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ._db import check_db
from app.api import get_router, register_exception_handlers
from app.core.config import Settings
from app.core.db import get_async_sessionmaker
from app.core.log import configure_logging
from app.core.metrics import PrometheusMiddleware, metrics_endpoint


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    configure_logging(settings.LOG_LEVEL, settings.LOG_FILE)
    await check_db(settings.database)

    sessionmaker = get_async_sessionmaker(settings.database, application_name=settings.NAME)
    app.state.sessionmaker = sessionmaker

    yield

    await sessionmaker.kw["bind"].dispose()


def init_app() -> FastAPI:
    settings = Settings()

    app = FastAPI(
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        title="Payment Processing API",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.include_router(get_router(), prefix="/api")

    app.add_middleware(PrometheusMiddleware)
    app.add_route("/metrics", metrics_endpoint, include_in_schema=False)

    register_exception_handlers(app)

    return app
