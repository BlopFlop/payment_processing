import contextlib

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import DatabaseSettings


def get_async_sessionmaker(
    db_config: DatabaseSettings,
    application_name: str = "UNKNOWN",
) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        url=db_config.build_url(),
        pool_size=db_config.POOL_SIZE,
        max_overflow=db_config.MAX_OVERFLOW,
        pool_timeout=db_config.POOL_RECYCLE,
        pool_pre_ping=db_config.POOL_PRE_PING,
        connect_args={"server_settings": {"application_name": application_name}},
    )
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=db_config.EXPIRE_ON_COMMIT,
        autocommit=db_config.AUTOCOMMIT,
        autoflush=db_config.AUTOFLUSH,
    )


@contextlib.asynccontextmanager
async def create_session(
    async_session_maker: async_sessionmaker[AsyncSession],
    autocommit: bool = True,
) -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session, session.begin():
        try:
            yield session

            if autocommit:
                await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
