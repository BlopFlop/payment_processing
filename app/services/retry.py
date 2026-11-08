import logging

from typing import Any

from faststream.rabbit import RabbitBroker, RabbitQueue

from app.core.broker import ATTEMPT_HEADER, DLQ_ROUTING_KEY, DLX_EXCHANGE, ERROR_HEADER
from app.core.metrics import MESSAGE_RETRIES


logger = logging.getLogger(__name__)


class Retry:
    def __init__(self, publisher: RabbitBroker, retry_queues: list[RabbitQueue]):
        self._publisher = publisher
        self._retry_queues = retry_queues

    @property
    def max_attempts(self) -> int:
        return len(self._retry_queues) + 1

    @staticmethod
    def attempt_from_headers(headers: dict[str, Any] | None) -> int:
        try:
            return int((headers or {}).get(ATTEMPT_HEADER, 0))
        except (TypeError, ValueError):
            return 0

    async def schedule(self, body: dict[str, Any], attempt: int, error: BaseException) -> None:
        error_text = f"{type(error).__name__}: {error}"[:500]

        if attempt < len(self._retry_queues):
            queue = self._retry_queues[attempt]
            logger.warning(
                "Попытка %s/%s не удалась, повтор через %s: %s",
                attempt + 1,
                self.max_attempts,
                queue.name,
                error_text,
            )
            await self._publisher.publish(
                body,
                queue=queue,
                headers={ATTEMPT_HEADER: attempt + 1, ERROR_HEADER: error_text},
                persist=True,
            )
            MESSAGE_RETRIES.labels("retry").inc()
            return

        logger.error("Исчерпаны %s попыток, отправляем в DLQ: %s body=%s", self.max_attempts, error_text, body)
        await self._publisher.publish(
            body,
            exchange=DLX_EXCHANGE,
            routing_key=DLQ_ROUTING_KEY,
            headers={ATTEMPT_HEADER: attempt + 1, ERROR_HEADER: error_text},
            persist=True,
        )
        MESSAGE_RETRIES.labels("dlq").inc()
