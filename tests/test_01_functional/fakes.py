from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import CreatePaymentRequest
from app.models import Payment, PaymentStatus
from tests.fixtures.payments import WEBHOOK_OK, payment_body


NOW = datetime(2026, 1, 1, 12, 0, 0)
PAYMENT_ID = UUID("550e8400-e29b-41d4-a716-446655440000")
IDEM_KEY = "order-12345"


def mk_payment(**overrides: Any) -> Payment:
    data: dict[str, Any] = dict(
        id=PAYMENT_ID,
        idempotency_key=IDEM_KEY,
        status=PaymentStatus.PENDING,
        amount=Decimal("100.50"),
        currency="RUB",
        description="Оплата заказа",
        metadata_={"order_id": "1"},
        webhook_url=WEBHOOK_OK,
        created_at=NOW,
        status_updated=NOW,
        processed_at=None,
    )
    data.update(overrides)
    return Payment(**data)


def mk_request_body(**overrides: Any) -> dict[str, Any]:
    return CreatePaymentRequest(**payment_body(**overrides)).model_dump(mode="json")


@asynccontextmanager
async def fake_session_factory() -> AsyncIterator[AsyncSession]:
    yield cast(AsyncSession, None)


class FakeBroker:
    def __init__(self, exc: Exception | None = None) -> None:
        self._exc = exc
        self.published: list[dict[str, Any]] = []

    async def publish(self, message: Any = None, queue: Any = "", exchange: Any = None, **kwargs: Any) -> None:
        if self._exc is not None:
            raise self._exc
        self.published.append(dict(message=message, queue=queue, exchange=exchange, **kwargs))
