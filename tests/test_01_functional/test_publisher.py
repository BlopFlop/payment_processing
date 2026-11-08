from typing import Any, cast

import pytest

from faststream.rabbit import RabbitBroker

from app.core.broker import NEW_ROUTING_KEY, PAYMENTS_EXCHANGE
from app.models import Event
from app.services._dto import OutboxDtoDB
from app.services.publisher import Publisher
from tests.test_01_functional.fakes import NOW, PAYMENT_ID, FakeBroker


def mk_outbox_dto(
    event_type: Event = Event.PAYMENT_CREATED, id: int = 7, payload: dict[str, Any] | None = None
) -> OutboxDtoDB:
    return OutboxDtoDB(
        id=id,
        event_type=event_type,
        payload=payload if payload is not None else {"payment_id": str(PAYMENT_ID)},
        is_processed=False,
        created_at=NOW,
        processed_at=None,
    )


@pytest.mark.parametrize(
    "event_type, error",
    (
        (Event.PAYMENT_CREATED, None),
        (Event.PAYMENT_SUCCEEDED, ValueError),
        (Event.PAYMENT_FAILED, ValueError),
    ),
)
async def test_publisher(event_type: Event, error: type[Exception] | None) -> None:
    broker = FakeBroker()
    dto = mk_outbox_dto(event_type)

    if error is not None:
        with pytest.raises(error):
            await Publisher(cast(RabbitBroker, broker)).publish(dto)
        assert not broker.published, "Событие без маршрута не должно публиковаться"
        return

    await Publisher(cast(RabbitBroker, broker)).publish(dto)

    assert len(broker.published) == 1, "Событие должно быть опубликовано один раз"
    published = broker.published[0]
    assert published["exchange"] == PAYMENTS_EXCHANGE, "Событие должно публиковаться в exchange payments"
    assert published["routing_key"] == NEW_ROUTING_KEY, f"Routing key должен быть {NEW_ROUTING_KEY}"
    assert published["message"] == {"payment_id": str(PAYMENT_ID), "event_id": 7}, (
        f"Неверное тело {published['message']}"
    )
    assert published["message_id"] == "7", "message_id должен совпадать с id события outbox"
    assert published["mandatory"] is True and published["persist"] is True, (
        "Публикация должна быть mandatory и persistent"
    )
