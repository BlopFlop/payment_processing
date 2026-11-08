from typing import Any
from uuid import UUID

import pytest

from app.models import Payment, PaymentStatus
from app.services import processor as processor_module
from app.services._dto import PaymentDtoDB
from app.services._schemas import WebhookPayload
from app.services.gateway import Gateway
from app.services.processor import PaymentProcessor
from tests.fixtures.payments import WEBHOOK_OK
from tests.test_01_functional.fakes import (
    NOW,
    PAYMENT_ID,
    fake_session_factory,
    mk_payment,
)


class FakeProcessorRepository:
    def __init__(self, payment: Payment | None = None, race_status: PaymentStatus | None = None) -> None:
        self.payment = payment
        self._race_status = race_status
        self.finalize_calls: list[dict[str, Any]] = []

    async def get(self, id: UUID) -> Payment | None:
        return self.payment

    async def finalize(self, id: UUID, expected_status: PaymentStatus, **values: Any) -> Payment | None:
        assert self.payment is not None, "finalize вызывается только для найденного платежа"
        self.finalize_calls.append(values)
        if self._race_status is not None:
            self.payment.status = self._race_status
            self.payment.processed_at = NOW
            return None
        if self.payment.status != expected_status:
            return None
        for key, value in values.items():
            setattr(self.payment, key, value)
        return self.payment


class FakeGateway(Gateway):
    def __init__(self, result: bool = True) -> None:
        self._result = result
        self.calls: list[UUID] = []

    async def charge(self, payment: PaymentDtoDB) -> bool:
        self.calls.append(payment.id)
        return self._result


class FakeWebhook:
    def __init__(self, exc: Exception | None = None) -> None:
        self._exc = exc
        self.calls: list[tuple[str, WebhookPayload]] = []

    async def send(self, url: str, payload: WebhookPayload) -> None:
        self.calls.append((url, payload))
        if self._exc is not None:
            raise self._exc


@pytest.mark.parametrize(
    "repo, gateway, webhook, expected_status, gateway_calls, error",
    (
        (FakeProcessorRepository(mk_payment()), FakeGateway(True), FakeWebhook(), PaymentStatus.SUCCEEDED, 1, None),
        (FakeProcessorRepository(mk_payment()), FakeGateway(False), FakeWebhook(), PaymentStatus.FAILED, 1, None),
        (
            FakeProcessorRepository(mk_payment(status=PaymentStatus.SUCCEEDED, processed_at=NOW)),
            FakeGateway(False),
            FakeWebhook(),
            PaymentStatus.SUCCEEDED,
            0,
            None,
        ),
        (
            FakeProcessorRepository(mk_payment(), race_status=PaymentStatus.FAILED),
            FakeGateway(True),
            FakeWebhook(),
            PaymentStatus.FAILED,
            1,
            None,
        ),
        (
            FakeProcessorRepository(mk_payment()),
            FakeGateway(True),
            FakeWebhook(RuntimeError("webhook down")),
            PaymentStatus.SUCCEEDED,
            1,
            RuntimeError,
        ),
    ),
)
async def test_processor_handle(
    monkeypatch: pytest.MonkeyPatch,
    repo: FakeProcessorRepository,
    gateway: FakeGateway,
    webhook: FakeWebhook,
    expected_status: PaymentStatus,
    gateway_calls: int,
    error: type[Exception] | None,
) -> None:
    monkeypatch.setattr(processor_module, "PaymentRepository", lambda session: repo)
    processor = PaymentProcessor(fake_session_factory, gateway, webhook)

    if error is not None:
        with pytest.raises(error):
            await processor.handle(PAYMENT_ID)
    else:
        await processor.handle(PAYMENT_ID)

    assert len(gateway.calls) == gateway_calls, (
        f"Шлюз должен быть вызван {gateway_calls} раз, а вызван {len(gateway.calls)}"
    )
    assert repo.payment is not None, "Платеж должен существовать"
    assert repo.payment.status == expected_status, (
        f"Статус платежа должен быть {expected_status}, а не {repo.payment.status}"
    )

    assert len(webhook.calls) == 1, f"Webhook должен быть отправлен 1 раз, а отправлен {len(webhook.calls)}"
    url, payload = webhook.calls[0]
    assert url == WEBHOOK_OK, f"Webhook должен уйти на {WEBHOOK_OK}, а ушёл на {url}"
    assert payload.status == expected_status, f"В webhook должен быть статус {expected_status}, а не {payload.status}"
    assert payload.event == f"payment.{expected_status}", f"Неверный тип события webhook {payload.event}"

    if gateway_calls:
        values = repo.finalize_calls[0]
        assert values["status"] == (PaymentStatus.SUCCEEDED if gateway._result else PaymentStatus.FAILED), (
            "В БД должен записываться результат шлюза"
        )
        assert values["processed_at"].tzinfo is None, "processed_at должен быть naive UTC (колонка без таймзоны)"


@pytest.mark.parametrize(
    "repo, gateway_calls, webhook_calls",
    (
        (FakeProcessorRepository(None), 0, 0),
        (FakeProcessorRepository(mk_payment(webhook_url=None)), 1, 0),
    ),
)
async def test_processor_skip(
    monkeypatch: pytest.MonkeyPatch,
    repo: FakeProcessorRepository,
    gateway_calls: int,
    webhook_calls: int,
) -> None:
    monkeypatch.setattr(processor_module, "PaymentRepository", lambda session: repo)
    gateway, webhook = FakeGateway(), FakeWebhook()

    await PaymentProcessor(fake_session_factory, gateway, webhook).handle(PAYMENT_ID)

    assert len(gateway.calls) == gateway_calls, (
        f"Шлюз должен быть вызван {gateway_calls} раз, а вызван {len(gateway.calls)}"
    )
    assert len(webhook.calls) == webhook_calls, (
        f"Webhook должен быть вызван {webhook_calls} раз, а вызван {len(webhook.calls)}"
    )
