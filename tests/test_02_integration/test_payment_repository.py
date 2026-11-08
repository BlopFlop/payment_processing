from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

import pytest

from app.models import PaymentStatus
from app.repository import PaymentRepository
from tests.fixtures.database import RemoveObject, SessionFactory
from tests.fixtures.payments import WEBHOOK_OK, CountPayments, GetPayment, PaymentFactory


def mk_payment_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = dict(
        idempotency_key=f"it-{uuid4()}",
        status=PaymentStatus.PENDING,
        amount=Decimal("100.50"),
        currency="RUB",
        description="test",
        metadata_={"order_id": "1"},
        webhook_url=WEBHOOK_OK,
    )
    data.update(overrides)
    return data


class TestPaymentRepository:
    async def test_create(
        self, session_factory: SessionFactory, get_payment: GetPayment, remove_object: RemoveObject
    ) -> None:
        async with session_factory() as session:
            payment = await PaymentRepository(session).create_if_not_exists(**mk_payment_data())

        try:
            assert payment is not None, "Создание платежа с новым ключом должно вернуть строку"
            assert payment.status == PaymentStatus.PENDING, f"Новый платеж должен быть pending, а не {payment.status}"
            assert payment.created_at is not None, "created_at должен заполняться БД"

            db_payment = await get_payment(payment.id)
            assert db_payment is not None, f"Платеж {payment.id} должен быть сохранён в БД после коммита"
        finally:
            if payment is not None:
                await remove_object(payment)

    async def test_create_conflict(
        self, session_factory: SessionFactory, count_payments: CountPayments, remove_object: RemoveObject
    ) -> None:
        data = mk_payment_data()

        async with session_factory() as session:
            first = await PaymentRepository(session).create_if_not_exists(**data)
        async with session_factory() as session:
            second = await PaymentRepository(session).create_if_not_exists(**{**data, "amount": Decimal("1.00")})

        try:
            assert first is not None, "Первая вставка должна создать платеж"
            assert second is None, "Вставка с занятым Idempotency-Key должна вернуть None (ON CONFLICT DO NOTHING)"
            count = await count_payments(data["idempotency_key"])
            assert count == 1, f"С одним ключом должен быть один платеж, а не {count}"
        finally:
            if first is not None:
                await remove_object(first)

    @pytest.mark.parametrize("exists", [True, False])
    async def test_get_by_idempotency_key(
        self, session: AsyncSession, payment_factory: PaymentFactory, exists: bool
    ) -> None:
        payment = await payment_factory()
        key = payment.idempotency_key if exists else f"missing-{uuid4()}"

        result = await PaymentRepository(session).get_by_idempotency_key(key)

        if exists:
            assert result is not None and result.id == payment.id, (
                f"По ключу {key} должен находиться платеж {payment.id}"
            )
        else:
            assert result is None, f"По несуществующему ключу {key} ничего не должно находиться"

    @pytest.mark.parametrize("status", [PaymentStatus.SUCCEEDED, PaymentStatus.FAILED])
    async def test_finalize(
        self,
        session_factory: SessionFactory,
        payment_factory: PaymentFactory,
        get_payment: GetPayment,
        status: PaymentStatus,
    ) -> None:
        payment = await payment_factory()

        async with session_factory() as session:
            first = await PaymentRepository(session).finalize(payment.id, PaymentStatus.PENDING, status=status)
        async with session_factory() as session:
            second = await PaymentRepository(session).finalize(
                payment.id,
                PaymentStatus.PENDING,
                status=PaymentStatus.FAILED,
            )

        assert first is not None and first.status == status, f"Первая финализация должна перевести платеж в {status}"
        assert second is None, "Повторная финализация уже не pending платежа должна вернуть None"

        db_payment = await get_payment(payment.id)

        assert db_payment is not None, f"Платеж {payment.id} должен существовать в БД"
        assert db_payment.status == status, f"В БД должен остаться результат первой финализации {status}"
