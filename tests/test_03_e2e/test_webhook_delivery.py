from httpx import AsyncClient

import pytest

from app.api.v1.schemas import CreatePaymentResponse
from app.core.broker import ATTEMPT_HEADER, ERROR_HEADER
from app.models import PaymentStatus
from tests.fixtures.broker import FetchMessage
from tests.fixtures.fakes import FakeGateway, FakeWebhookServer
from tests.fixtures.payments import WEBHOOK_HOST, payment_body
from tests.test_03_e2e.helpers import (
    create_payment,
    find_in_dlq,
    new_key,
    parse,
    wait_final,
    wait_webhooks,
)


pytestmark = pytest.mark.usefixtures("e2e_stack")


async def test_webhook_retry_then_delivered(
    client: AsyncClient,
    fake_gateway: FakeGateway,
    webhook_server: FakeWebhookServer,
    fetch_message: FetchMessage,
) -> None:
    response = await create_payment(client, new_key(), payment_body(webhook_url=f"{WEBHOOK_HOST}/flaky"))
    payment_id = parse(response, CreatePaymentResponse).payment_id

    calls = await wait_webhooks(webhook_server, payment_id, 2)

    assert [c.status_code for c in calls] == [500, 200], (
        f"Ожидалась неудачная попытка и успешный повтор, а получено {[c.status_code for c in calls]}"
    )
    assert fake_gateway.calls_for(payment_id) == 1, "Повтор из-за webhook не должен повторно вызывать шлюз"
    assert (await wait_final(client, payment_id)).status == PaymentStatus.SUCCEEDED, "Платеж должен быть succeeded"
    assert await find_in_dlq(fetch_message, payment_id, timeout=1) is None, (
        "Доставленное сообщение не должно попасть в DLQ"
    )


async def test_webhook_failure_goes_to_dlq(
    client: AsyncClient,
    fake_gateway: FakeGateway,
    webhook_server: FakeWebhookServer,
    fetch_message: FetchMessage,
) -> None:
    response = await create_payment(client, new_key(), payment_body(webhook_url=f"{WEBHOOK_HOST}/fail"))
    payment_id = parse(response, CreatePaymentResponse).payment_id

    message = await find_in_dlq(fetch_message, payment_id)

    assert message is not None, "После 3 неудачных попыток сообщение должно оказаться в DLQ"
    assert message.headers[ATTEMPT_HEADER] == 3, f"В DLQ должно быть 3 попытки, а не {message.headers[ATTEMPT_HEADER]}"
    assert "HTTPStatusError" in message.headers[ERROR_HEADER], f"В DLQ должна сохраниться ошибка: {message.headers}"

    calls = webhook_server.calls_for(payment_id)
    assert [c.status_code for c in calls] == [500, 500, 500], f"Должно быть 3 попытки webhook, а было {len(calls)}"
    assert fake_gateway.calls_for(payment_id) == 1, "Повторы не должны повторно вызывать шлюз"

    payment = await wait_final(client, payment_id)
    assert payment.status == PaymentStatus.SUCCEEDED, "Ошибка webhook не должна влиять на статус платежа"
