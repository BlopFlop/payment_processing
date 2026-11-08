import json

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import httpx

import pytest

from app.services._dto import PaymentDtoDB
from app.services.gateway import Gateway


class FakeGateway(Gateway):
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def charge(self, payment: PaymentDtoDB) -> bool:
        self.calls.append(str(payment.id))
        return bool((payment.metadata_ or {}).get("gateway_success", True))

    def calls_for(self, payment_id: UUID | str) -> int:
        return self.calls.count(str(payment_id))


@dataclass
class WebhookCall:
    path: str
    payload: dict[str, Any]
    headers: dict[str, str]
    status_code: int


@dataclass
class FakeWebhookServer:
    calls: list[WebhookCall] = field(default_factory=list)
    _attempts: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def handler(self, request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        payment_id = payload["payment_id"]
        self._attempts[payment_id] += 1

        path = request.url.path
        if path == "/ok":
            status_code = 200
        elif path == "/fail":
            status_code = 500
        elif path == "/flaky":
            status_code = 500 if self._attempts[payment_id] == 1 else 200
        else:
            status_code = 404

        self.calls.append(WebhookCall(path, payload, dict(request.headers), status_code))
        return httpx.Response(status_code)

    def calls_for(self, payment_id: UUID | str) -> list[WebhookCall]:
        return [call for call in self.calls if call.payload["payment_id"] == str(payment_id)]


@pytest.fixture(scope="session")
def fake_gateway() -> FakeGateway:
    return FakeGateway()


@pytest.fixture(scope="session")
def webhook_server() -> FakeWebhookServer:
    return FakeWebhookServer()
