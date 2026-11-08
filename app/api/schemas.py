from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"status": "ok"}]})

    status: Literal["ok"] = Field(default="ok", description="Положительный ответ на запрос healthcheck")


class ErrorResponse(BaseModel):
    detail: str = Field(..., description="Человекочитаемое описание ошибки")


class UnauthorizedError(ErrorResponse):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"detail": "Invalid or missing API key"}]},
    )


class PaymentNotFoundError(ErrorResponse):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"detail": "Payment 550e8400-e29b-41d4-a716-446655440000 not found"}]},
    )


class IdempotencyConflictError(ErrorResponse):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"detail": "Idempotency-Key 'order-12345' was already used with a different request body"}],
        },
    )
