from collections.abc import AsyncIterator, Awaitable, Callable
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import pytest

from app.models import Event, Outbox, Payment, PaymentStatus
from tests.fixtures.database import MkObject, RemoveObjects


WEBHOOK_HOST = "https://webhook.test"
WEBHOOK_OK = f"{WEBHOOK_HOST}/ok"

PaymentFactory = Callable[..., Awaitable[Payment]]
OutboxFactory = Callable[..., Awaitable[Outbox]]
GetPayment = Callable[[UUID | str], Awaitable[Payment | None]]
CountPayments = Callable[[str], Awaitable[int]]
GetOutboxForPayment = Callable[[UUID | str], Awaitable[list[Outbox]]]


def payment_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "amount": "100.50",
        "currency": "RUB",
        "description": "Оплата заказа",
        "metadata": {"order_id": "1"},
        "webhook_url": WEBHOOK_OK,
    }
    body.update(overrides)
    return body


@pytest.fixture(scope="function")
async def payment_factory(mk_object: MkObject, remove_objects: RemoveObjects) -> AsyncIterator[PaymentFactory]:
    created: list[Payment] = []

    async def factory(**overrides: Any) -> Payment:
        data: dict[str, Any] = dict(
            id=uuid4(),
            idempotency_key=f"test-{uuid4()}",
            status=PaymentStatus.PENDING,
            amount=Decimal("100.00"),
            currency="RUB",
            description="test",
            metadata_={},
            webhook_url=WEBHOOK_OK,
        )
        data.update(overrides)
        obj = Payment(**data)
        await mk_object(obj)
        created.append(obj)
        return obj

    yield factory

    await remove_objects(created)


@pytest.fixture(scope="function")
async def outbox_factory(mk_object: MkObject, remove_objects: RemoveObjects) -> AsyncIterator[OutboxFactory]:
    created: list[Outbox] = []

    async def factory(**overrides: Any) -> Outbox:
        data: dict[str, Any] = dict(
            event_type=Event.PAYMENT_CREATED,
            payload={"payment_id": str(uuid4())},
            is_processed=False,
        )
        data.update(overrides)
        obj = Outbox(**data)
        await mk_object(obj)
        created.append(obj)
        return obj

    yield factory

    await remove_objects(created)


@pytest.fixture(scope="session")
def get_payment(local_sessionmaker: async_sessionmaker[AsyncSession]) -> GetPayment:
    async def func_(payment_id: UUID | str) -> Payment | None:
        async with local_sessionmaker() as session:
            return await session.get(Payment, UUID(str(payment_id)))

    return func_


@pytest.fixture(scope="session")
def count_payments(local_sessionmaker: async_sessionmaker[AsyncSession]) -> CountPayments:
    async def func_(idempotency_key: str) -> int:
        async with local_sessionmaker() as session:
            query = select(func.count()).select_from(Payment).where(Payment.idempotency_key == idempotency_key)
            return await session.scalar(query) or 0

    return func_


@pytest.fixture(scope="session")
def get_outbox_for_payment(local_sessionmaker: async_sessionmaker[AsyncSession]) -> GetOutboxForPayment:
    async def func_(payment_id: UUID | str) -> list[Outbox]:
        async with local_sessionmaker() as session:
            query = (
                select(Outbox).where(Outbox.payload["payment_id"].as_string() == str(payment_id)).order_by(Outbox.id)
            )
            return list((await session.scalars(query)).all())

    return func_
