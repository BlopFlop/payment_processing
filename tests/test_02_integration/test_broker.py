from datetime import datetime
from uuid import uuid4

import pytest
import aio_pika

from faststream.rabbit import RabbitBroker, RabbitQueue

from app.core.broker import (
    ATTEMPT_HEADER,
    ERROR_HEADER,
    NEW_ROUTING_KEY,
    PAYMENTS_DLQ,
    PAYMENTS_EXCHANGE,
    PAYMENTS_NEW_QUEUE,
)
from app.models import Event
from app.services._dto import OutboxDtoDB
from app.services.publisher import Publisher
from app.services.retry import Retry
from tests.fixtures.broker import FetchMessage


class TestBroker:
    async def test_publisher(self, broker: RabbitBroker, purge_queues: None, fetch_message: FetchMessage) -> None:
        payment_id = str(uuid4())
        dto = OutboxDtoDB(
            id=42,
            event_type=Event.PAYMENT_CREATED,
            payload={"payment_id": payment_id},
            is_processed=False,
            created_at=datetime.now(),
            processed_at=None,
        )

        await Publisher(broker).publish(dto)
        message = await fetch_message(PAYMENTS_NEW_QUEUE)

        assert message is not None, "Опубликованное событие должно попасть в очередь payments.new"
        assert message.body == {"payment_id": payment_id, "event_id": 42}, f"Неверное тело сообщения {message.body}"
        assert message.message_id == "42", "message_id должен совпадать с id события outbox"
        assert message.delivery_mode == 2, "Сообщение должно быть persistent"

    async def test_unroutable_raises(self, broker: RabbitBroker) -> None:
        with pytest.raises(aio_pika.exceptions.DeliveryError):
            await broker.publish({"x": 1}, exchange=PAYMENTS_EXCHANGE, routing_key="unknown.route", mandatory=True)

    @pytest.mark.parametrize("attempt", [0, 1])
    async def test_retry_returns_to_new_queue(
        self,
        broker: RabbitBroker,
        retry_queues: list[RabbitQueue],
        purge_queues: None,
        fetch_message: FetchMessage,
        attempt: int,
    ) -> None:
        body = {"payment_id": str(uuid4()), "event_id": 1}

        await Retry(broker, retry_queues).schedule(body, attempt, RuntimeError("boom"))
        message = await fetch_message(PAYMENTS_NEW_QUEUE, timeout=5)

        assert message is not None, "После TTL retry-очереди сообщение должно вернуться в payments.new"
        assert message.body == body, "Тело сообщения должно сохраниться"
        assert message.headers[ATTEMPT_HEADER] == attempt + 1, (
            f"Заголовок {ATTEMPT_HEADER} должен быть {attempt + 1}, а не {message.headers[ATTEMPT_HEADER]}"
        )
        assert message.headers[ERROR_HEADER] == "RuntimeError: boom", "Должна передаваться последняя ошибка"
        assert await fetch_message(PAYMENTS_DLQ, timeout=0) is None, "До исчерпания попыток в DLQ ничего быть не должно"

    async def test_retry_exhausted_to_dlq(
        self, broker: RabbitBroker, retry_queues: list[RabbitQueue], purge_queues: None, fetch_message: FetchMessage
    ) -> None:
        body = {"payment_id": str(uuid4()), "event_id": 1}

        await Retry(broker, retry_queues).schedule(body, 2, RuntimeError("boom"))
        message = await fetch_message(PAYMENTS_DLQ)

        assert message is not None, "После 3-й неудачной попытки сообщение должно попасть в DLQ"
        assert message.body == body and message.headers[ATTEMPT_HEADER] == 3, (
            "В DLQ должно быть сообщение с 3 попытками"
        )
        assert await fetch_message(PAYMENTS_NEW_QUEUE, timeout=0.5) is None, "Сообщение не должно вернуться в обработку"

    async def test_rejected_goes_to_dlq(
        self, broker: RabbitBroker, purge_queues: None, fetch_message: FetchMessage
    ) -> None:
        await broker.publish({"garbage": True}, exchange=PAYMENTS_EXCHANGE, routing_key=NEW_ROUTING_KEY)

        queue = await broker.declare_queue(PAYMENTS_NEW_QUEUE)
        raw = await queue.get(timeout=5)
        await raw.reject(requeue=False)

        message = await fetch_message(PAYMENTS_DLQ)
        assert message is not None and message.body == {"garbage": True}, "Отклонённое сообщение должно попасть в DLQ"
