import logging

from typing import Protocol

import httpx

from ._schemas import WebhookPayload


logger = logging.getLogger(__name__)


class WebhookSender(Protocol):
    async def send(self, url: str, payload: WebhookPayload) -> None: ...


class HttpWebhookSender:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def send(self, url: str, payload: WebhookPayload) -> None:
        response = await self._client.post(
            url,
            json=payload.model_dump(mode="json"),
            headers={"X-Webhook-Id": f"{payload.payment_id}:{payload.status.value}"},
        )
        response.raise_for_status()
        logger.info("Webhook %s -> %s %s", payload.payment_id, url, response.status_code)
