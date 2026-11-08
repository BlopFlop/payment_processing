import logging

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ._dto import PaymentDtoDB
from ._schemas import WebhookPayload
from .gateway import Gateway
from .webhook import WebhookSender
from app.core.metrics import GATEWAY_DURATION, PAYMENTS_PROCESSED, WEBHOOK_DELIVERIES
from app.models import PaymentStatus
from app.repository import PaymentRepository


logger = logging.getLogger(__name__)


class PaymentProcessor:
    def __init__(
        self,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
        gateway: Gateway,
        webhook: WebhookSender,
    ):
        self._session_factory = session_factory
        self._gateway = gateway
        self._webhook = webhook

    async def _load(self, payment_id: UUID) -> PaymentDtoDB | None:
        async with self._session_factory() as session:
            payment_db = await PaymentRepository(session).get(payment_id)
            return PaymentDtoDB.from_orm(payment_db) if payment_db else None

    async def _charge(self, payment: PaymentDtoDB) -> PaymentDtoDB:
        with GATEWAY_DURATION.time():
            succeeded = await self._gateway.charge(payment)
        status = PaymentStatus.SUCCEEDED if succeeded else PaymentStatus.FAILED
        now = datetime.now(UTC).replace(tzinfo=None)

        async with self._session_factory() as session:
            repo = PaymentRepository(session)
            payment_db = await repo.finalize(
                payment.id,
                expected_status=PaymentStatus.PENDING,
                status=status,
                processed_at=now,
                status_updated=now,
            )
            if payment_db is None:
                logger.info("Payment %s уже финализирован другим обработчиком", payment.id)
                payment_db = await repo.get(payment.id)
            else:
                PAYMENTS_PROCESSED.labels(str(status)).inc()
                logger.info("Payment %s processed: %s", payment.id, status)
            return PaymentDtoDB.from_orm(payment_db)

    async def handle(self, payment_id: UUID) -> None:
        payment = await self._load(payment_id)

        if payment is None:
            logger.warning("Payment %s not found, skipping", payment_id)
            return

        if payment.status == PaymentStatus.PENDING:
            payment = await self._charge(payment)

        if not payment.webhook_url:
            logger.info("У платежа %s нет webhook_url, уведомление не отправляется", payment_id)
            return

        payload = WebhookPayload(
            event=f"payment.{payment.status}",
            payment_id=payment.id,
            status=payment.status,
            amount=payment.amount,
            currency=payment.currency,
            metadata=payment.metadata_,
            processed_at=payment.processed_at,
        )
        try:
            await self._webhook.send(payment.webhook_url, payload)
        except Exception:
            WEBHOOK_DELIVERIES.labels("failure").inc()
            raise
        WEBHOOK_DELIVERIES.labels("success").inc()
        logger.info("Webhook для платежа %s доставлен", payment_id)
