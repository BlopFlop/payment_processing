import asyncio
import logging

from asyncio import Event
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ._dto import OutboxDtoDB, OutboxDtoUpdate
from .publisher import EventPublisher
from app.core.metrics import OUTBOX_EVENTS
from app.repository import OutboxRepository


logger = logging.getLogger(__name__)


class RelayService:
    def __init__(
        self,
        publisher: EventPublisher,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
        batch_size: int = 1_000,
        interval: float = 1.0,
    ):
        self._publisher = publisher
        self._session_factory = session_factory

        self._batch_size = batch_size
        self._interval = interval

        self._event = Event()

    async def _wait(self) -> None:
        try:
            await asyncio.wait_for(self._event.wait(), timeout=self._interval)
        except TimeoutError:
            pass

    def _mk_ext_payload(self, outbox_dto: OutboxDtoDB, exc: Exception) -> dict[str, Any]:
        payload = deepcopy(outbox_dto.payload)
        payload["attempts"] = outbox_dto.payload.get("attempts", 0) + 1
        payload["last_err_time"] = datetime.now(UTC).isoformat()
        payload["last_err"] = f"{type(exc).__name__}: {exc}"[:1000]
        return payload

    async def _outbox_process(self) -> int:
        published = 0

        async with self._session_factory() as session:
            outbox_repo = OutboxRepository(session)

            items_db = await outbox_repo.get_unpublished(self._batch_size)
            logger.debug("Получен батч размером %s", len(items_db))

            for item_db in items_db:
                dto = OutboxDtoDB.from_orm(item_db)

                try:
                    await self._publisher.publish(dto)
                except Exception as exc:
                    logger.warning("Возникла ошибка при публикации события id %s %s", dto.id, exc)
                    update_dto = OutboxDtoUpdate(payload=self._mk_ext_payload(dto, exc))
                    OUTBOX_EVENTS.labels("failed").inc()
                else:
                    update_dto = OutboxDtoUpdate(
                        is_processed=True,
                        processed_at=datetime.now(UTC).replace(tzinfo=None),
                    )
                    published += 1
                    OUTBOX_EVENTS.labels("published").inc()

                await outbox_repo.update(item_db, **update_dto.as_dict())

        if published:
            logger.info("Опубликовано %s событий", published)
        return published

    async def start(self) -> None:
        logger.info("Relay запущен")
        while not self._event.is_set():
            try:
                published = await self._outbox_process()
            except Exception:
                logger.exception("Ошибка в цикле relay")
                published = 0

            if published < self._batch_size:
                await self._wait()
        logger.info("Relay остановлен")

    def stop(self) -> None:
        if not self._event.is_set():
            self._event.set()
