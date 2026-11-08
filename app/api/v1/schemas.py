import uuid

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class Currency(StrEnum):
    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"


class CreatePaymentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(
        ...,
        gt=0,
        max_digits=18,
        decimal_places=2,
        description="Сумма платежа (> 0, не более 2 знаков после запятой)",
        examples=["1500.50"],
    )
    currency: Currency = Field(
        ...,
        description="Валюта платежа",
        examples=["RUB"],
    )
    description: str | None = Field(
        None,
        max_length=1024,
        description="Назначение платежа или описание для пользователя",
        examples=["Оплата заказа №12345"],
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Дополнительные произвольные данные по платежу в формате JSON",
        examples=[{"order_id": "12345", "user_id": "user_999"}],
    )
    webhook_url: HttpUrl = Field(
        ...,
        description="Адрес для отправки асинхронного уведомления о финальном статусе",
        examples=["https://example.com/webhooks/payments"],
    )


class CreatePaymentResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    payment_id: uuid.UUID = Field(
        ...,
        description="Уникальный идентификатор созданного платежа",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    status: str = Field(
        ...,
        description="Текущий статус платежа",
        examples=["pending"],
    )
    created_at: datetime = Field(
        ...,
        description="Дата и время создания платежа",
        examples=["2024-05-20T12:00:00Z"],
    )


class CheckStatusRequest(BaseModel):
    payment_id: uuid.UUID = Field(
        ...,
        description="Уникальный идентификатор платежа",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )


class CheckStatusResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    payment_id: uuid.UUID = Field(
        ...,
        description="Уникальный идентификатор платежа",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    amount: Decimal = Field(
        ...,
        description="Сумма платежа",
        examples=[1500.50],
    )
    currency: str = Field(
        ...,
        description="Трехбуквенный код валюты",
        examples=["RUB"],
    )
    description: str | None = Field(
        None,
        description="Назначение платежа",
        examples=["Оплата заказа №12345"],
    )
    status: str = Field(
        ...,
        description="Текущий статус платежа",
        examples=["succeeded"],
    )
    metadata: dict[str, Any] | None = Field(
        None,
        description="Дополнительные данные",
        examples=[{"order_id": "12345"}],
    )
    webhook_url: str | None = Field(
        None,
        description="Адрес для уведомления о результате",
        examples=["https://example.com/webhooks/payments"],
    )
    created_at: datetime = Field(
        ...,
        description="Дата и время создания платежа",
        examples=["2024-05-20T12:00:00Z"],
    )
    processed_at: datetime | None = Field(
        None,
        description="Дата и время финальной обработки",
        examples=["2024-05-20T12:01:00Z"],
    )
