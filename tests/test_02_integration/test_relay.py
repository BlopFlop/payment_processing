from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from faststream.rabbit import RabbitBroker

from app.core.broker import PAYMENTS_NEW_QUEUE
from app.models import Event, Outbox
from app.services.publisher import Publisher
from app.services.relay import RelayService
from tests.fixtures.broker import FetchAllMessages
from tests.fixtures.database import SessionFactory
from tests.fixtures.payments import OutboxFactory


class TestRelayService:
    async def test_publishes_and_marks(
        self,
        clean_db: None,
        purge_queues: None,
        broker: RabbitBroker,
        session_factory: SessionFactory,
        local_sessionmaker: async_sessionmaker[AsyncSession],
        outbox_factory: OutboxFactory,
        fetch_all_messages: FetchAllMessages,
    ) -> None:
        items = [await outbox_factory() for _ in range(3)]
        relay = RelayService(Publisher(broker), session_factory, batch_size=10)

        published = await relay._outbox_process()

        assert published == 3, f"Relay должен опубликовать 3 события, а опубликовал {published}"

        async with local_sessionmaker() as session:
            rows = (await session.scalars(select(Outbox).order_by(Outbox.id))).all()
        assert all(row.is_processed and row.processed_at for row in rows), (
            "Все события должны быть помечены опубликованными"
        )

        messages = await fetch_all_messages(PAYMENTS_NEW_QUEUE)
        assert [m.body["event_id"] for m in messages] == [item.id for item in items], (
            "В очередь должны попасть все события в порядке создания"
        )

    async def test_unroutable_event_stays_in_outbox(
        self,
        clean_db: None,
        purge_queues: None,
        broker: RabbitBroker,
        session_factory: SessionFactory,
        local_sessionmaker: async_sessionmaker[AsyncSession],
        outbox_factory: OutboxFactory,
        fetch_all_messages: FetchAllMessages,
    ) -> None:
        item = await outbox_factory(event_type=Event.PAYMENT_SUCCEEDED)
        relay = RelayService(Publisher(broker), session_factory, batch_size=10)

        published = await relay._outbox_process()

        async with local_sessionmaker() as session:
            row = await session.get(Outbox, item.id)
            assert row is not None, f"Событие {item.id} должно остаться в outbox"

        assert published == 0, "Событие без маршрута не должно считаться опубликованным"
        assert row.is_processed is False, "Неопубликованное событие должно остаться в outbox"
        assert row.payload["attempts"] == 1 and "ValueError" in row.payload["last_err"], (
            f"В payload должны сохраниться счётчик попыток и ошибка, а не {row.payload}"
        )
        assert await fetch_all_messages(PAYMENTS_NEW_QUEUE) == [], "В очередь ничего не должно попасть"
