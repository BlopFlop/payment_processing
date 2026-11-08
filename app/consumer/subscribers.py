import logging

from typing import Any

from faststream import Context
from faststream.rabbit import RabbitBroker


logger = logging.getLogger(__name__)


def get_subscribers(broker: RabbitBroker) -> None:
    from .schemas import PaymentCreatedEvent
    from app.core import PAYMENTS_EXCHANGE, PAYMENTS_NEW_QUEUE
    from app.services.processor import PaymentProcessor
    from app.services.retry import Retry

    @broker.subscriber(PAYMENTS_NEW_QUEUE, PAYMENTS_EXCHANGE)
    async def handle_payment_created(
        event: PaymentCreatedEvent,
        processor: PaymentProcessor = Context("processor"),
        retry_policy: Retry = Context("retry"),
        headers: dict[str, Any] = Context("message.headers"),
    ) -> None:
        attempt = Retry.attempt_from_headers(headers)
        logger.info("Обработка платежа %s (Вызовов %s)", event.payment_id, attempt)
        try:
            await processor.handle(event.payment_id)
        except Exception as exc:
            await retry_policy.schedule(event.model_dump(mode="json"), attempt, exc)
