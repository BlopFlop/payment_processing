from decimal import Decimal
from typing import Any
from uuid import UUID

from httpx import AsyncClient
from pydantic import BaseModel

import pytest

from app.api.schemas import (
    ErrorResponse,
    IdempotencyConflictError,
    PaymentNotFoundError,
    UnauthorizedError,
)
from app.api.v1.schemas import CheckStatusResponse, CreatePaymentResponse
from tests.fixtures.payments import CountPayments, payment_body
from tests.test_03_e2e.helpers import PAYMENTS_URL, create_payment, new_key, parse


pytestmark = pytest.mark.usefixtures("e2e_stack")


@pytest.mark.parametrize(
    "anonymous, headers, body, status_code, model, loc",
    (
        (True, {"Idempotency-Key": "k"}, payment_body(), 401, UnauthorizedError, None),
        (False, {"Idempotency-Key": "k", "X-API-Key": "wrong"}, payment_body(), 401, UnauthorizedError, None),
        (False, {}, payment_body(), 422, None, ["header", "Idempotency-Key"]),
        (False, {"Idempotency-Key": "k"}, payment_body(amount="-1"), 422, None, ["body", "amount"]),
        (False, {"Idempotency-Key": "k"}, payment_body(amount="1.001"), 422, None, ["body", "amount"]),
        (False, {"Idempotency-Key": "k"}, payment_body(currency="GBP"), 422, None, ["body", "currency"]),
        (
            False,
            {"Idempotency-Key": "k"},
            payment_body(webhook_url="not-url"),
            422,
            None,
            ["body", "webhook_url"],
        ),
        (False, {"Idempotency-Key": "k"}, payment_body(foo="bar"), 422, None, ["body", "foo"]),
    ),
)
async def test_create_rejected(
    client: AsyncClient,
    anon_client: AsyncClient,
    count_payments: CountPayments,
    anonymous: bool,
    headers: dict[str, str],
    body: dict[str, Any],
    status_code: int,
    model: type[BaseModel] | None,
    loc: list[str] | None,
) -> None:
    key = new_key()
    headers = {name: key if name == "Idempotency-Key" else value for name, value in headers.items()}

    response = await (anon_client if anonymous else client).post(PAYMENTS_URL, json=body, headers=headers)

    assert response.status_code == status_code, (
        f"Должен вернуться {status_code}, а не {response.status_code}: {response.text}"
    )
    if model is not None:
        parse(response, model)
    if loc is not None:
        locs = [item["loc"] for item in response.json()["detail"]]
        assert loc in locs, f"Ошибка валидации должна указывать на {loc}, а указывает на {locs}"

    assert await count_payments(key) == 0, "Отклонённый запрос не должен создавать платеж"


async def test_idempotency_conflict(client: AsyncClient, count_payments: CountPayments) -> None:
    key = new_key()
    first = await create_payment(client, key, payment_body())
    conflict = await create_payment(client, key, payment_body(amount="1.00"))

    assert conflict.status_code == 409, f"Тот же ключ с другим телом должен вернуть 409, а не {conflict.status_code}"
    error = parse(conflict, IdempotencyConflictError)
    assert key in error.detail, f"В ошибке должен быть ключ {key}: {error.detail}"

    assert await count_payments(key) == 1, "Конфликтующий запрос не должен создавать платеж"
    payment_id = parse(first, CreatePaymentResponse).payment_id
    payment = parse(await client.get(f"{PAYMENTS_URL}/{payment_id}"), CheckStatusResponse)
    assert payment.amount == Decimal("100.50"), f"Сумма исходного платежа не должна измениться: {payment.amount}"


MISSING_ID = UUID("00000000-0000-4000-8000-000000000000")


@pytest.mark.parametrize(
    "anonymous, payment_id, status_code, model, detail",
    (
        (True, MISSING_ID, 401, UnauthorizedError, "Invalid or missing API key"),
        (False, MISSING_ID, 404, PaymentNotFoundError, f"Payment {MISSING_ID} not found"),
        (False, "not-a-uuid", 422, None, None),
    ),
)
async def test_get_rejected(
    client: AsyncClient,
    anon_client: AsyncClient,
    anonymous: bool,
    payment_id: UUID | str,
    status_code: int,
    model: type[ErrorResponse] | None,
    detail: str | None,
) -> None:
    response = await (anon_client if anonymous else client).get(f"{PAYMENTS_URL}/{payment_id}")

    assert response.status_code == status_code, f"Должен вернуться {status_code}, а не {response.status_code}"
    if model is not None:
        error = parse(response, model)
        assert error.detail == detail, f"Сообщение ошибки должно быть {detail!r}, а не {error.detail!r}"
    else:
        locs = [item["loc"] for item in response.json()["detail"]]
        assert ["path", "payment_id"] in locs, f"Ошибка должна указывать на payment_id, а указывает на {locs}"
