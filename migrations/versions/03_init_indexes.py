"""init tables

Revision ID: 03
Revises: 02
Create Date: 2026-11-07 20:10:36.449701

"""

from collections.abc import Sequence

from alembic import op


revision: str = "03"
down_revision: str | Sequence[str] | None = "02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_outbox_unprocessed_id
                ON outbox (id)
                WHERE is_processed = false
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_outbox_unprocessed_id")
