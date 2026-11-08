from collections.abc import Awaitable, Callable, Sequence
from contextlib import AbstractAsyncContextManager

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import pytest

from app.models import Outbox, Payment


Model = Payment | Outbox

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]
MkObject = Callable[[Model], Awaitable[None]]
MkObjects = Callable[[Sequence[Model]], Awaitable[None]]
RemoveObject = Callable[[Model], Awaitable[None]]
RemoveObjects = Callable[[Sequence[Model]], Awaitable[None]]


@pytest.fixture(scope="session")
def mk_object(local_sessionmaker: async_sessionmaker[AsyncSession]) -> MkObject:
    async def func(obj: Model) -> None:
        async with local_sessionmaker() as session:
            session.add(obj)
            await session.commit()
            await session.refresh(obj)

    return func


@pytest.fixture(scope="session")
def mk_objects(local_sessionmaker: async_sessionmaker[AsyncSession]) -> MkObjects:
    async def func(objects: Sequence[Model]) -> None:
        async with local_sessionmaker() as session:
            session.add_all(objects)
            await session.commit()
            for obj in objects:
                await session.refresh(obj)

    return func


@pytest.fixture(scope="session")
def remove_objects(local_sessionmaker: async_sessionmaker[AsyncSession]) -> RemoveObjects:

    async def func(objects: Sequence[Model]) -> None:
        payment_ids = [obj.id for obj in objects if isinstance(obj, Payment)]
        outbox_ids = [obj.id for obj in objects if isinstance(obj, Outbox)]

        async with local_sessionmaker() as session:
            if payment_ids:
                await session.execute(delete(Payment).where(Payment.id.in_(payment_ids)))
            if outbox_ids:
                await session.execute(delete(Outbox).where(Outbox.id.in_(outbox_ids)))
            await session.commit()

    return func


@pytest.fixture(scope="session")
def remove_object(remove_objects: RemoveObjects) -> RemoveObject:
    async def func(obj: Model) -> None:
        await remove_objects([obj])

    return func


@pytest.fixture(scope="function")
async def clean_db(local_sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with local_sessionmaker() as session:
        await session.execute(text("TRUNCATE payments, outbox RESTART IDENTITY"))
        await session.commit()
