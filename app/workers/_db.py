import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import DatabaseSettings


logger = logging.getLogger(__name__)


async def check_db(db_config: DatabaseSettings, attempts: int = 5, delay: float = 2.0) -> None:
    engine = create_async_engine(
        url=db_config.build_url(),
        pool_size=db_config.POOL_SIZE,
        max_overflow=db_config.MAX_OVERFLOW,
        pool_timeout=db_config.POOL_RECYCLE,
        pool_pre_ping=db_config.POOL_PRE_PING,
        connect_args={"server_settings": {"application_name": "db_checker"}},
    )
    try:
        for attempt in range(1, attempts + 1):
            try:
                async with asyncio.timeout(5):
                    async with engine.connect() as conn:
                        await conn.execute(text("SELECT 1"))
                logger.info("Database is available")
                return
            except (OSError, SQLAlchemyError, TimeoutError) as exc:
                logger.warning("DB check %s/%s failed: %s", attempt, attempts, exc)
                if attempt == attempts:
                    raise RuntimeError("Database is unavailable") from exc
                await asyncio.sleep(delay)
    finally:
        await engine.dispose()
