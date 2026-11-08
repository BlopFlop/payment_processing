import asyncio

import pytest

from app.models import PaymentStatus
from app.services._dto import PaymentDtoDB
from app.services._schemas import WebhookPayload
from app.services.gateway import Gateway
from app.services.processor import PaymentProcessor
from tests.fixtures.database import SessionFactory
from tests.fixtures.payments import GetPayment, PaymentFactory


class FakeGateway(Gateway):
    def __init__(self, results: list[bool], delay: float = 0.0) -> None:
        self._results = list(results)
        self._delay = delay
        self.calls = 0

    async def charge(self, payment: PaymentDtoDB) -> bool:
        result = self._results[self.calls % len(self._results)]
        self.calls += 1
        await asyncio.sleep(self._delay)
        return result


class FakeWebhook:
    def __init__(self) -> None:
        self.calls: list[WebhookPayload] = []

    async def send(self, url: str, payload: WebhookPayload) -> None:
        self.calls.append(payload)


class TestPaymentProcessor:
    @pytest.mark.parametrize(
        "gateway_result, expected_status",
        (
            (True, PaymentStatus.SUCCEEDED),
            (False, PaymentStatus.FAILED),
        ),
    )
    async def test_handle(
        self,
        session_factory: SessionFactory,
        payment_factory: PaymentFactory,
        get_payment: GetPayment,
        gateway_result: bool,
        expected_status: PaymentStatus,
    ) -> None:
        payment = await payment_factory()
        webhook = FakeWebhook()

        await PaymentProcessor(session_factory, FakeGateway([gateway_result]), webhook).handle(payment.id)

        db_payment = await get_payment(payment.id)

        assert db_payment is not None, f"Платеж {payment.id} должен существовать в БД"
        assert db_payment.status == expected_status, (
            f"Статус в БД должен быть {expected_status}, а не {db_payment.status}"
        )
        assert db_payment.processed_at is not None, "processed_at должен быть заполнен"
        assert [c.status for c in webhook.calls] == [expected_status], (
            "Webhook должен уйти один раз с итоговым статусом"
        )

    async def test_redelivery_charges_once(
        self, session_factory: SessionFactory, payment_factory: PaymentFactory
    ) -> None:
        payment = await payment_factory()
        gateway, webhook = FakeGateway([True]), FakeWebhook()
        processor = PaymentProcessor(session_factory, gateway, webhook)

        await processor.handle(payment.id)
        await processor.handle(payment.id)

        assert gateway.calls == 1, (
            f"Повторная доставка не должна списывать деньги повторно, вызовов шлюза: {gateway.calls}"
        )
        assert len(webhook.calls) == 2, "Webhook при повторной доставке отправляется повторно (at-least-once)"

    async def test_concurrent_deliveries_single_result(
        self, session_factory: SessionFactory, payment_factory: PaymentFactory, get_payment: GetPayment
    ) -> None:
        payment = await payment_factory()
        gateway, webhook = FakeGateway([True, False], delay=0.1), FakeWebhook()
        processor = PaymentProcessor(session_factory, gateway, webhook)

        await asyncio.gather(processor.handle(payment.id), processor.handle(payment.id))

        db_payment = await get_payment(payment.id)

        assert db_payment is not None, f"Платеж {payment.id} должен существовать в БД"
        assert db_payment.status in (PaymentStatus.SUCCEEDED, PaymentStatus.FAILED), "Платеж должен быть финализирован"
        statuses = [c.status for c in webhook.calls]
        assert set(statuses) == {db_payment.status}, (
            f"Оба webhook должны сообщать сохранённый статус {db_payment.status}, а не {statuses}"
        )
