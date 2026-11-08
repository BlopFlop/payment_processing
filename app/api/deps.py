from collections.abc import AsyncGenerator

from fastapi import Depends, FastAPI, Request, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.db import create_session
from app.repository import OutboxRepository, PaymentRepository
from app.services.security import verify_api_key


def get_app(request: Request) -> FastAPI:
    app: FastAPI = request.app
    return app


def get_settings(app: FastAPI = Depends(get_app)) -> Settings:
    settings: Settings = app.state.settings
    return settings


def get_sessionmaker(app: FastAPI = Depends(get_app)) -> async_sessionmaker[AsyncSession]:
    sessionmaker: async_sessionmaker[AsyncSession] = app.state.sessionmaker
    return sessionmaker


async def get_session(
    sessionmaker: async_sessionmaker[AsyncSession] = Depends(get_sessionmaker),
) -> AsyncGenerator[AsyncSession, None]:
    async with create_session(sessionmaker) as session:
        yield session


def get_payment_repository(session: AsyncSession = Depends(get_session)) -> PaymentRepository:
    return PaymentRepository(session)


def get_outbox_repository(session: AsyncSession = Depends(get_session)) -> OutboxRepository:
    return OutboxRepository(session)


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def auth(
    api_key: str | None = Security(api_key_header),
    settings: Settings = Depends(get_settings),
) -> None:
    verify_api_key(api_key, settings.API_KEY.get_secret_value())
