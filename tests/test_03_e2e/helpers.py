import asyncio

from typing import Any
from uuid import UUID, uuid4

from httpx import AsyncClient, Response
from pydantic import BaseModel, ValidationError

import pytest

from app.api.v1.schemas import CheckStatusResponse
from app.core.broker import PAYMENTS_DLQ
from app.models import PaymentStatus
from tests.fixtures.broker import FetchMessage, ReceivedMessage
from tests.fixtures.fakes import FakeWebhookServer, WebhookCall
from tests.utils import wait_for


PAYMENTS_URL = "/v1/payments"


def new_key() -> str:
    return f"e2e-{uuid4()}"


def parse[M: BaseModel](response: Response, model: type[M]) -> M:
    try:
        return model.model_validate(response.json())
    except ValidationError:
        pytest.fail(f"Тело ответа должно сериализоваться схемой {model.__name__}, а пришло {response.text}")


async def create_payment(client: AsyncClient, key: str, body: dict[str, Any]) -> Response:
    return await client.post(PAYMENTS_URL, json=body, headers={"Idempotency-Key": key})


async def wait_final(client: AsyncClient, payment_id: UUID | str) -> CheckStatusResponse:
    async def final() -> CheckStatusResponse | None:
        response = await client.get(f"{PAYMENTS_URL}/{payment_id}")
        payment = parse(response, CheckStatusResponse)
        return payment if payment.status != PaymentStatus.PENDING else None

    return await wait_for(final, f"Платеж {payment_id} должен перейти в финальный статус")


async def wait_webhooks(webhook_server: FakeWebhookServer, payment_id: UUID | str, count: int) -> list[WebhookCall]:
    async def delivered() -> list[WebhookCall] | None:
        calls = webhook_server.calls_for(payment_id)
        return calls if len(calls) >= count else None

    await wait_for(delivered, f"Для платежа {payment_id} должно быть {count} запросов webhook")
    await asyncio.sleep(0.5)
    return webhook_server.calls_for(payment_id)


async def find_in_dlq(
    fetch_message: FetchMessage, payment_id: UUID | str, timeout: float = 15.0
) -> ReceivedMessage | None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        message = await fetch_message(PAYMENTS_DLQ, timeout=0.5)
        if message is not None and message.body.get("payment_id") == str(payment_id):
            return message
    return None
