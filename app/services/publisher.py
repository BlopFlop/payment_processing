import logging

from typing import Protocol

from faststream.rabbit import RabbitBroker

from ._dto import OutboxDtoDB
from app.core.broker import NEW_ROUTING_KEY, PAYMENTS_EXCHANGE
from app.models import Event


logger = logging.getLogger(__name__)


ROUTING: dict[Event, str] = {
    Event.PAYMENT_CREATED: NEW_ROUTING_KEY,
}


class EventPublisher(Protocol):
    async def publish(self, outbox_dto: OutboxDtoDB) -> None: ...


class Publisher:
    def __init__(self, broker: RabbitBroker) -> None:
        self._broker = broker

    async def publish(self, outbox_dto: OutboxDtoDB) -> None:
        routing_key = ROUTING.get(outbox_dto.event_type)
        if routing_key is None:
            raise ValueError(f"Нет маршрута для события {outbox_dto.event_type!r}")

        await self._broker.publish(
            {**outbox_dto.payload, "event_id": outbox_dto.id},
            exchange=PAYMENTS_EXCHANGE,
            routing_key=routing_key,
            message_id=str(outbox_dto.id),
            mandatory=True,
            persist=True,
        )
        logger.info("Event_id %s опубликован", outbox_dto.id)
