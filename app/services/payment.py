import logging

from typing import Any
from uuid import UUID

from ._dto import OutboxDtoCreate, OutboxDtoDB, PaymentDtoCreate, PaymentDtoDB, PaymentFingerprint
from .exceptions import IdempotencyConflict, PaymentNotFound
from app.core.metrics import PAYMENTS_CREATED, PAYMENTS_IDEMPOTENCY
from app.models import Event
from app.repository import OutboxRepository, PaymentRepository


logger = logging.getLogger(__name__)


class PaymentService:
    def __init__(self) -> None:
        self.payment_repo: PaymentRepository
        self.outbox_repo: OutboxRepository

    async def create(self, idempotency_key: str, body: dict[str, Any]) -> PaymentDtoDB:
        dto_create_payment = PaymentDtoCreate(
            metadata_=body.pop("metadata", None) or {}, idempotency_key=idempotency_key, **body
        )
        logger.debug(
            "Создание платежа idem_key=%s amount=%s %s",
            dto_create_payment.idempotency_key,
            dto_create_payment.amount,
            dto_create_payment.currency,
        )

        payment_db = await self.payment_repo.create_if_not_exists(**dto_create_payment.as_json_dict())

        if payment_db is None:
            return await self._replay(dto_create_payment)

        payment_dto_db = PaymentDtoDB.from_orm(payment_db)
        outbox_dto_create = OutboxDtoCreate(
            event_type=Event.PAYMENT_CREATED, payload=dict(payment_id=payment_dto_db.id)
        )
        outbox_db = await self.outbox_repo.create(**outbox_dto_create.as_json_dict())
        outbox_dto_db = OutboxDtoDB.from_orm(outbox_db)
        PAYMENTS_CREATED.labels(str(payment_dto_db.currency)).inc()

        logger.debug(
            "Outbox создан id=%s type=%s aggregate_id=%s",
            outbox_dto_db.id,
            outbox_dto_db.event_type,
            payment_dto_db.id,
        )
        logger.info(
            "Payment создан id=%s idem_key=%s amount=%s %s",
            payment_dto_db.id,
            payment_dto_db.idempotency_key,
            payment_dto_db.amount,
            payment_dto_db.currency,
        )
        return payment_dto_db

    async def _replay(self, request: PaymentDtoCreate) -> PaymentDtoDB:
        existing = await self.payment_repo.get_by_idempotency_key(request.idempotency_key)
        if existing is None:
            raise IdempotencyConflict(request.idempotency_key)

        existing_dto = PaymentDtoDB.from_orm(existing)
        if PaymentFingerprint.model_validate(existing_dto) != PaymentFingerprint.model_validate(request):
            PAYMENTS_IDEMPOTENCY.labels("conflict").inc()
            logger.warning("Конфликт идемпотентности idem_key=%s: другое тело запроса", request.idempotency_key)
            raise IdempotencyConflict(request.idempotency_key)

        PAYMENTS_IDEMPOTENCY.labels("replay").inc()
        logger.info("Повторный запрос idem_key=%s -> payment %s", request.idempotency_key, existing_dto.id)
        return existing_dto

    async def get(self, payment_id: UUID) -> PaymentDtoDB:
        logger.debug("Получение Payment id=%s", payment_id)
        payment_db = await self.payment_repo.get_by_id(payment_id)

        if not payment_db:
            logger.info("Payment не существует id=%s", payment_id)
            raise PaymentNotFound(payment_id)

        return PaymentDtoDB.from_orm(payment_db)
