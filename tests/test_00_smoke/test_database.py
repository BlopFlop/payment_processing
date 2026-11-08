from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import pytest

from alembic.config import Config
from alembic.script import ScriptDirectory

from app import models
from tests.conftest import PROJECT_FOLDER


@pytest.mark.parametrize("table_name", [models.Payment.__tablename__, models.Outbox.__tablename__, "alembic_version"])
async def test_db_table(session: AsyncSession, table_name: str) -> None:
    has_tab_query = text("""\
    SELECT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_name = :table_name
    );
    """)
    cursor = await session.execute(has_tab_query, {"table_name": table_name})
    result = cursor.scalar_one()
    assert result, f"Таблица {table_name} не создана."


@pytest.mark.parametrize(
    "table_name, index_name",
    (
        ("payments", "payments_pkey"),
        ("payments", "payments_idempotency_key_key"),
        ("outbox", "outbox_pkey"),
        ("outbox", "ix_outbox_unprocessed_id"),
    ),
)
async def test_db_index(session: AsyncSession, table_name: str, index_name: str) -> None:
    query = text("SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE tablename = :table AND indexname = :index)")
    result = (await session.execute(query, {"table": table_name, "index": index_name})).scalar_one()
    assert result, f"Индекс {index_name} на таблице {table_name} не создан."


async def test_migrations_head(session: AsyncSession) -> None:
    head = ScriptDirectory.from_config(Config(str(PROJECT_FOLDER / "alembic.ini"))).get_current_head()
    current = (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
    assert current == head, f"БД должна быть на последней миграции {head=}, а находится на {current=}"
