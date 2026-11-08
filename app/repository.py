from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Base, Outbox, Payment, PaymentStatus


class SqlBaseRepository[T: Base]:
    def __init__(self, model: type[T], session: AsyncSession) -> None:
        self._model = model
        self._session = session

    async def get_by_id(self, id: int | UUID) -> T | None:
        return await self._session.get(self._model, id)

    async def get_all(self) -> list[T]:
        return await self.get_by_filters()

    async def add(self, obj: T) -> None:
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj)

    async def create(self, **kwargs: Any) -> T:
        query = insert(self._model).values(**kwargs).returning(self._model)
        result = await self._session.execute(query)
        return result.scalars().one()

    async def update(self, obj: T, **kwargs: Any) -> T:
        for key, value in kwargs.items():
            setattr(obj, key, value)
        await self.add(obj)
        return obj

    async def remove(self, obj: T) -> None:
        await self._session.delete(obj)

    async def get_by_filters(self, **kwargs: Any) -> list[T]:
        conditions = self._mk_conditions(kwargs)
        query = select(self._model).where(*conditions)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    def _mk_conditions(self, kwargs: dict[str, Any]) -> list[ColumnElement[bool]]:
        conditions = []
        for key, value in kwargs.items():
            column_elt: ColumnElement[Any] = getattr(self._model, key)
            condition = column_elt.in_(value) if isinstance(value, list) else column_elt == value
            conditions.append(condition)
        return conditions


class PaymentRepository(SqlBaseRepository[Payment]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Payment, session)

    async def create_if_not_exists(self, **kwargs: Any) -> Payment | None:
        query = (
            pg_insert(self._model)
            .values(**kwargs)
            .on_conflict_do_nothing(index_elements=[self._model.idempotency_key])
            .returning(self._model)
        )
        result = await self._session.execute(query)
        return result.scalars().one_or_none()

    async def get(self, id: UUID) -> Payment | None:
        return await self._session.get(self._model, id, populate_existing=True)

    async def get_by_idempotency_key(self, idempotency_key: str) -> Payment | None:
        query = select(self._model).where(self._model.idempotency_key == idempotency_key)
        result = await self._session.execute(query)
        return result.scalars().one_or_none()

    async def finalize(self, id: UUID, expected_status: PaymentStatus, **values: Any) -> Payment | None:
        query = (
            update(self._model)
            .where(self._model.id == id, self._model.status == expected_status)
            .values(**values)
            .returning(self._model)
            .execution_options(populate_existing=True)
        )
        result = await self._session.execute(query)
        return result.scalars().one_or_none()


class OutboxRepository(SqlBaseRepository[Outbox]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Outbox, session)

    async def get_unpublished(self, limit: int = 1_000) -> list[Outbox]:
        query = (
            select(self._model)
            .with_for_update(skip_locked=True)
            .where(self._model.is_processed.is_(False))
            .order_by(self._model.id.asc())
            .limit(limit)
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())
