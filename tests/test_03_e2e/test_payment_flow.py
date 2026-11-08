from decimal import Decimal

from httpx import AsyncClient

import pytest

from app.api.v1.schemas import CreatePaymentResponse
from app.models import PaymentStatus
from tests.fixtures.fakes import FakeGateway, FakeWebhookServer
from tests.fixtures.payments import CountPayments, GetOutboxForPayment, payment_body
from tests.test_03_e2e.helpers import (
    create_payment,
    new_key,
    parse,
    wait_final,
    wait_webhooks,
)


pytestmark = pytest.mark.usefixtures("e2e_stack")


@pytest.mark.parametrize(
    "gateway_success, expected_status",
    (
        (True, PaymentStatus.SUCCEEDED),
        (False, PaymentStatus.FAILED),
    ),
)
async def test_payment_flow(
    client: AsyncClient,
    fake_gateway: FakeGateway,
    webhook_server: FakeWebhookServer,
    get_outbox_for_payment: GetOutboxForPayment,
    gateway_success: bool,
    expected_status: PaymentStatus,
) -> None:
    body = payment_body(metadata={"order_id": "42", "gateway_success": gateway_success})

    response = await create_payment(client, new_key(), body)

    assert response.status_code == 202, (
        f"Создание платежа должно вернуть 202, а не {response.status_code}: {response.text}"
    )
    created = parse(response, CreatePaymentResponse)
    assert created.status == PaymentStatus.PENDING, f"Новый платеж должен быть pending, а не {created.status}"

    payment = await wait_final(client, created.payment_id)
    assert payment.status == expected_status, f"Итоговый статус должен быть {expected_status}, а не {payment.status}"
    assert payment.amount == Decimal("100.50") and payment.currency == "RUB", "Сумма и валюта должны сохраниться"
    assert payment.metadata == body["metadata"], f"metadata должна сохраниться без изменений: {payment.metadata}"
    assert payment.webhook_url == body["webhook_url"], "webhook_url должен сохраниться"
    assert payment.processed_at is not None, "После обработки должен быть заполнен processed_at"

    calls = await wait_webhooks(webhook_server, created.payment_id, 1)
    assert len(calls) == 1, f"Webhook должен быть доставлен один раз, а отправлен {len(calls)} раз"
    call = calls[0]
    assert call.path == "/ok" and call.status_code == 200, f"Webhook должен уйти на /ok и получить 200: {call}"
    assert call.payload["event"] == f"payment.{expected_status}", f"Неверное событие webhook {call.payload['event']}"
    assert call.payload["status"] == expected_status, f"В webhook должен быть статус {expected_status}"
    assert call.payload["amount"] == "100.50", f"В webhook должна быть сумма 100.50, а не {call.payload['amount']}"
    assert call.headers["x-webhook-id"] == f"{created.payment_id}:{expected_status}", "Неверный X-Webhook-Id"

    assert fake_gateway.calls_for(created.payment_id) == 1, "Шлюз должен быть вызван ровно один раз"
    outbox = await get_outbox_for_payment(created.payment_id)
    assert len(outbox) == 1 and outbox[0].is_processed, "Событие платежа в outbox должно быть одно и опубликовано"


async def test_idempotent_replay(
    client: AsyncClient,
    fake_gateway: FakeGateway,
    webhook_server: FakeWebhookServer,
    count_payments: CountPayments,
    get_outbox_for_payment: GetOutboxForPayment,
) -> None:
    key, body = new_key(), payment_body()

    first = await create_payment(client, key, body)
    second = await create_payment(client, key, body)

    assert first.status_code == second.status_code == 202, (
        f"Оба запроса должны вернуть 202, а вернули {first.status_code} и {second.status_code}"
    )
    first_id = parse(first, CreatePaymentResponse).payment_id
    assert parse(second, CreatePaymentResponse).payment_id == first_id, "Повтор должен вернуть тот же payment_id"

    await wait_final(client, first_id)
    calls = await wait_webhooks(webhook_server, first_id, 1)

    assert await count_payments(key) == 1, "Повтор не должен создавать второй платеж"
    assert len(await get_outbox_for_payment(first_id)) == 1, "Повтор не должен создавать второе событие"
    assert fake_gateway.calls_for(first_id) == 1, "Деньги должны списываться один раз"
    assert len(calls) == 1, f"Webhook должен быть отправлен один раз, а не {len(calls)}"
