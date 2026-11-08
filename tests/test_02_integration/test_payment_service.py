import asyncio

from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

import pytest

from app.api.v1.schemas import CreatePaymentRequest
from app.models import Event
from app.repository import OutboxRepository, PaymentRepository
from app.services._dto import PaymentDtoDB
from app.services.exceptions import IdempotencyConflict
from app.services.payment import PaymentService
from tests.fixtures.database import SessionFactory
from tests.fixtures.payments import CountPayments, GetOutboxForPayment, GetPayment, payment_body


def mk_request_body(**overrides: Any) -> dict[str, Any]:
    return CreatePaymentRequest(**payment_body(**overrides)).model_dump(mode="json")


def mk_service(session: AsyncSession) -> PaymentService:
    service = PaymentService()
    service.payment_repo = PaymentRepository(session)
    service.outbox_repo = OutboxRepository(session)
    return service


class FailingOutboxRepository:
    async def create(self, **kwargs: Any) -> None:
        raise RuntimeError("outbox insert failed")


class TestPaymentService:
    async def test_create_writes_payment_and_outbox(
        self, session_factory: SessionFactory, get_payment: GetPayment, get_outbox_for_payment: GetOutboxForPayment
    ) -> None:
        key = f"it-{uuid4()}"
        async with session_factory() as session:
            dto = await mk_service(session).create(key, mk_request_body())

        payment = await get_payment(dto.id)
        outbox = await get_outbox_for_payment(dto.id)

        assert payment is not None, "Платеж должен быть сохранён"
        assert payment.amount == Decimal("100.50") and payment.currency == "RUB", "Данные платежа должны сохраниться"
        assert len(outbox) == 1, f"В outbox должно быть одно событие по платежу, а не {len(outbox)}"
        assert outbox[0].event_type == Event.PAYMENT_CREATED, "Событие должно быть payment.created"
        assert outbox[0].is_processed is False, "Событие должно ждать публикации"

    async def test_create_rollback(self, session_factory: SessionFactory, count_payments: CountPayments) -> None:
        key = f"it-{uuid4()}"
        with pytest.raises(RuntimeError):
            async with session_factory() as session:
                service = mk_service(session)
                service.outbox_repo = cast(OutboxRepository, FailingOutboxRepository())
                await service.create(key, mk_request_body())

        count = await count_payments(key)
        assert count == 0, "При ошибке записи в outbox платеж не должен сохраниться"

    async def test_replay_and_conflict(
        self,
        session_factory: SessionFactory,
        count_payments: CountPayments,
        get_outbox_for_payment: GetOutboxForPayment,
    ) -> None:
        key = f"it-{uuid4()}"
        async with session_factory() as session:
            first = await mk_service(session).create(key, mk_request_body())
        async with session_factory() as session:
            replay = await mk_service(session).create(key, mk_request_body())

        assert replay.id == first.id, "Повтор с тем же телом должен вернуть тот же платеж"

        with pytest.raises(IdempotencyConflict):
            async with session_factory() as session:
                await mk_service(session).create(key, mk_request_body(amount="1.00"))

        assert await count_payments(key) == 1, "С одним ключом должен существовать один платеж"
        assert len(await get_outbox_for_payment(first.id)) == 1, "Повторы не должны создавать новых событий"

    async def test_concurrent_same_key(
        self,
        session_factory: SessionFactory,
        count_payments: CountPayments,
        get_outbox_for_payment: GetOutboxForPayment,
    ) -> None:
        key = f"it-{uuid4()}"

        async def create() -> PaymentDtoDB:
            async with session_factory() as session:
                return await mk_service(session).create(key, mk_request_body())

        first, second = await asyncio.gather(create(), create())

        assert first.id == second.id, "Одновременные запросы с одним ключом должны вернуть один платеж"
        assert await count_payments(key) == 1, "Должен быть создан ровно один платеж"
        assert len(await get_outbox_for_payment(first.id)) == 1, "Должно быть создано ровно одно событие"
