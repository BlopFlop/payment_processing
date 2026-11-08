from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repository import OutboxRepository
from tests.fixtures.payments import OutboxFactory


class TestOutboxRepository:
    async def test_get_unpublished(
        self, clean_db: None, local_sessionmaker: async_sessionmaker[AsyncSession], outbox_factory: OutboxFactory
    ) -> None:
        items = [await outbox_factory(is_processed=i % 3 == 0) for i in range(1, 8)]
        unprocessed_ids = [item.id for item in items if not item.is_processed]

        async with local_sessionmaker() as session, session.begin():
            repo = OutboxRepository(session)
            limited = await repo.get_unpublished(limit=3)
            everything = await repo.get_unpublished(limit=100)

        assert [i.id for i in limited] == unprocessed_ids[:3], (
            f"Должны вернуться первые 3 неопубликованных события по возрастанию id: {unprocessed_ids[:3]}"
        )
        assert [i.id for i in everything] == unprocessed_ids, "Опубликованные события не должны выбираться"

    async def test_get_unpublished_skip_locked(
        self, clean_db: None, local_sessionmaker: async_sessionmaker[AsyncSession], outbox_factory: OutboxFactory
    ) -> None:
        items = [await outbox_factory() for _ in range(5)]

        async with local_sessionmaker() as session_a, local_sessionmaker() as session_b:
            async with session_a.begin(), session_b.begin():
                batch_a = await OutboxRepository(session_a).get_unpublished(limit=3)
                batch_b = await OutboxRepository(session_b).get_unpublished(limit=10)

        ids_a, ids_b = {i.id for i in batch_a}, {i.id for i in batch_b}
        assert not ids_a & ids_b, f"Батчи двух relay не должны пересекаться: {ids_a & ids_b}"
        assert ids_a | ids_b == {i.id for i in items}, "Вместе батчи должны покрыть все неопубликованные события"
