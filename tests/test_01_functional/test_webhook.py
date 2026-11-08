from decimal import Decimal

import httpx

import pytest

from app.models import PaymentStatus
from app.services._schemas import WebhookPayload
from app.services.webhook import HttpWebhookSender
from tests.fixtures.payments import WEBHOOK_OK
from tests.test_01_functional.fakes import NOW, PAYMENT_ID


WEBHOOK_PAYLOAD = WebhookPayload(
    event="payment.succeeded",
    payment_id=PAYMENT_ID,
    status=PaymentStatus.SUCCEEDED,
    amount=Decimal("100.50"),
    currency="RUB",
    metadata={"order_id": "1"},
    processed_at=NOW,
)


@pytest.mark.parametrize(
    "status_code, error",
    (
        (200, None),
        (201, None),
        (204, None),
        (400, httpx.HTTPStatusError),
        (404, httpx.HTTPStatusError),
        (500, httpx.HTTPStatusError),
        (503, httpx.HTTPStatusError),
    ),
)
async def test_webhook_sender(status_code: int, error: type[Exception] | None) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status_code)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        sender = HttpWebhookSender(client)
        if error is not None:
            with pytest.raises(error):
                await sender.send(WEBHOOK_OK, WEBHOOK_PAYLOAD)
        else:
            await sender.send(WEBHOOK_OK, WEBHOOK_PAYLOAD)

    assert len(requests) == 1, "Webhook должен отправляться одним запросом"
    request = requests[0]
    assert request.method == "POST" and str(request.url) == WEBHOOK_OK, (
        f"Неверный запрос {request.method} {request.url}"
    )
    assert request.headers["X-Webhook-Id"] == f"{PAYMENT_ID}:succeeded", (
        "X-Webhook-Id должен быть <payment_id>:<status>"
    )
    assert httpx.Response(200, content=request.content).json() == WEBHOOK_PAYLOAD.model_dump(mode="json"), (
        "Тело webhook должно совпадать с WebhookPayload"
    )
