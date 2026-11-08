import asyncio

from datetime import datetime
from typing import Any
from uuid import uuid4

import pytest

from app.models import Event, Outbox
from app.services import relay as relay_module
from app.services._dto import OutboxDtoDB
from app.services.relay import RelayService
from tests.test_01_functional.fakes import NOW, fake_session_factory


class FakeRelayOutboxRepository:
    def __init__(self, items: list[Outbox], exc: Exception | None = None) -> None:
        self._items = items
        self._exc = exc
        self.limits: list[int] = []
        self.updates: dict[int, dict[str, Any]] = {}

    async def get_unpublished(self, limit: int) -> list[Outbox]:
        self.limits.append(limit)
        if self._exc is not None:
            raise self._exc
        return self._items[:limit]

    async def update(self, obj: Outbox, **kwargs: Any) -> Outbox:
        self.updates[obj.id] = kwargs
        return obj


class FakePublisher:
    def __init__(self, fail_ids: set[int] | None = None) -> None:
        self._fail_ids = fail_ids or set()
        self.published: list[int] = []

    async def publish(self, dto: OutboxDtoDB) -> None:
        if dto.id in self._fail_ids:
            raise RuntimeError("broker down")
        self.published.append(dto.id)


def mk_outbox_items(count: int, payload: dict[str, Any] | None = None) -> list[Outbox]:
    return [
        Outbox(
            id=i,
            event_type=Event.PAYMENT_CREATED,
            payload=dict(payload or {"payment_id": str(uuid4())}),
            is_processed=False,
            created_at=NOW,
            processed_at=None,
        )
        for i in range(1, count + 1)
    ]


@pytest.mark.parametrize(
    "items, fail_ids, batch_size, expected_published, expected_attempts",
    (
        (mk_outbox_items(3), set(), 10, [1, 2, 3], None),
        (mk_outbox_items(5), set(), 2, [1, 2], None),
        (mk_outbox_items(0), set(), 10, [], None),
        (mk_outbox_items(3), {2}, 10, [1, 3], 1),
        (mk_outbox_items(1, payload={"payment_id": "x", "attempts": 2}), {1}, 10, [], 3),
    ),
)
async def test_relay_outbox_process(
    monkeypatch: pytest.MonkeyPatch,
    items: list[Outbox],
    fail_ids: set[int],
    batch_size: int,
    expected_published: list[int],
    expected_attempts: int | None,
) -> None:
    repo = FakeRelayOutboxRepository(items)
    publisher = FakePublisher(fail_ids)
    monkeypatch.setattr(relay_module, "OutboxRepository", lambda session: repo)
    relay = RelayService(publisher, fake_session_factory, batch_size=batch_size)

    published = await relay._outbox_process()

    assert repo.limits == [batch_size], f"Relay должен запрашивать батч размером {batch_size}, а запросил {repo.limits}"
    assert published == len(expected_published), f"Опубликовано должно быть {len(expected_published)}, а не {published}"
    assert publisher.published == expected_published, f"Порядок публикации должен быть {expected_published}"

    for item_id in expected_published:
        update = repo.updates[item_id]
        assert update["is_processed"] is True, f"Событие {item_id} должно быть помечено опубликованным"
        assert isinstance(update["processed_at"], datetime), f"У события {item_id} должно быть заполнено processed_at"

    for item_id in fail_ids:
        update = repo.updates[item_id]
        assert "is_processed" not in update, f"Неопубликованное событие {item_id} не должно помечаться опубликованным"
        assert update["payload"]["attempts"] == expected_attempts, (
            f"Счётчик попыток события {item_id} должен быть {expected_attempts}, а не {update['payload']['attempts']}"
        )
        assert update["payload"]["last_err"] == "RuntimeError: broker down", (
            "В payload должна сохраняться последняя ошибка"
        )


async def test_relay_survives_errors_and_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = FakeRelayOutboxRepository([], exc=ConnectionError("db down"))
    monkeypatch.setattr(relay_module, "OutboxRepository", lambda session: repo)
    relay = RelayService(FakePublisher(), fake_session_factory, batch_size=10, interval=0.01)

    task = asyncio.create_task(relay.start())
    while len(repo.limits) < 3:
        await asyncio.sleep(0.01)
    assert not task.done(), "Relay не должен падать из-за ошибки в итерации"

    relay.stop()
    await asyncio.wait_for(task, timeout=1)
    assert task.done() and task.exception() is None, "Relay должен корректно завершиться после stop()"
