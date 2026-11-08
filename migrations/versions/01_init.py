"""init

Revision ID: 01
Revises:
Create Date: 2026-11-07 20:08:05.092296

"""

from collections.abc import Sequence


revision: str = "01"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
