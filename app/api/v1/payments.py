import uuid

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Header, Path


def get_payments_router() -> APIRouter:
    from ..deps import auth
    from ..schemas import (
        IdempotencyConflictError,
        PaymentNotFoundError,
        UnauthorizedError,
    )
    from .deps import build_payment_service
    from .schemas import (
        CheckStatusResponse,
        CreatePaymentRequest,
        CreatePaymentResponse,
    )
    from app.services import PaymentService

    router = APIRouter(tags=["payment"], dependencies=[Depends(auth)])

    @router.post(
        "",
        status_code=202,
        summary="Создание платежа",
        description=(
            "Создает новый платеж. Требует заголовок `Idempotency-Key`. "
            "Повтор с тем же ключом и тем же телом возвращает уже созданный платеж; "
            "тот же ключ с другим телом — 409."
        ),
        response_description="Платеж принят в обработку",
        responses={
            401: {"model": UnauthorizedError, "description": "Нет заголовка `X-API-Key` или ключ неверный"},
            409: {"model": IdempotencyConflictError, "description": "`Idempotency-Key` уже использован с другим телом"},
        },
    )
    @router.post("/", status_code=202, include_in_schema=False)
    async def mk_payment(
        idempotency_key: Annotated[
            str,
            Header(
                alias="Idempotency-Key",
                min_length=1,
                max_length=255,
                description="Уникальный ключ запроса. Повтор с тем же ключом не создаёт новый платеж.",
                examples=["order-12345"],
            ),
        ],
        service: PaymentService = Depends(build_payment_service),
        data: CreatePaymentRequest = Body(...),
    ) -> CreatePaymentResponse:
        dto = await service.create(idempotency_key, data.model_dump(mode="json"))
        return CreatePaymentResponse(payment_id=dto.id, status=dto.status, created_at=dto.created_at)

    @router.get(
        "/{payment_id}",
        status_code=200,
        summary="Получение информации о платеже",
        description="Возвращает детальную информацию о платеже по его идентификатору.",
        response_description="Детальная информация о платеже",
        responses={
            401: {"model": UnauthorizedError, "description": "Нет заголовка `X-API-Key` или ключ неверный"},
            404: {"model": PaymentNotFoundError, "description": "Платеж не найден"},
        },
    )
    async def get_payment(
        payment_id: uuid.UUID = Path(..., description="Уникальный идентификатор платежа"),
        service: PaymentService = Depends(build_payment_service),
    ) -> CheckStatusResponse:
        dto = await service.get(payment_id)
        return CheckStatusResponse(
            payment_id=dto.id,
            amount=dto.amount,
            currency=dto.currency,
            description=dto.description,
            status=dto.status,
            metadata=dto.metadata_,
            webhook_url=dto.webhook_url,
            created_at=dto.created_at,
            processed_at=dto.processed_at,
        )

    return router
