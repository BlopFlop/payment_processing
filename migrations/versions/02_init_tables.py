"""init tables

Revision ID: 02
Revises: 01
Create Date: 2026-11-07 20:08:36.449701

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "02"
down_revision: str | Sequence[str] | None = "01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outbox",
        sa.Column(
            "id", sa.BigInteger(), autoincrement=True, nullable=False, comment="Уникальный идентификатор события"
        ),
        sa.Column(
            "event_type",
            sa.Enum("PAYMENT_CREATED", "PAYMENT_SUCCEEDED", "PAYMENT_FAILED", name="event"),
            nullable=False,
            comment="Тип бизнес-события (например: payment.succeeded)",
        ),
        sa.Column(
            "payload", sa.JSON(), nullable=False, comment="Тело сообщения (данные события) для отправки в брокер"
        ),
        sa.Column(
            "is_processed",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="Флаг обработки события релеем / воркером отправки",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("NOW()"),
            nullable=False,
            comment="Время генерации события",
        ),
        sa.Column(
            "processed_at", sa.DateTime(), nullable=True, comment="Время успешной отправки события в брокер сообщений"
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Таблица исходящих событий для реализации паттерна Transactional Outbox",
    )
    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False, comment="Уникальный идентификатор платежа в системе"),
        sa.Column(
            "idempotency_key",
            sa.String(),
            nullable=False,
            comment="Ключ идемпотентности для предотвращения дублирования транзакций",
        ),
        sa.Column(
            "status",
            sa.Enum("PENDING", "SUCCEEDED", "FAILED", name="paymentstatus"),
            nullable=False,
            comment="Текущий статус платежа",
        ),
        sa.Column(
            "amount",
            sa.DECIMAL(precision=18, scale=2),
            nullable=False,
            comment="Сумма платежа с фиксированной точностью",
        ),
        sa.Column("currency", sa.String(), nullable=False, comment="Валюта платежа"),
        sa.Column(
            "description", sa.String(), nullable=True, comment="Назначение платежа или описание для пользователя"
        ),
        sa.Column(
            "metadata_",
            sa.JSON(),
            nullable=False,
            comment="Дополнительные произвольные данные по платежу в формате JSON",
        ),
        sa.Column(
            "webhook_url",
            sa.String(),
            nullable=True,
            comment="Адрес для отправки асинхронного уведомления о финальном статусе",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("NOW()"),
            nullable=False,
            comment="Дата и время создания платежа",
        ),
        sa.Column(
            "status_updated",
            sa.DateTime(),
            server_default=sa.text("NOW()"),
            nullable=False,
            comment="Дата и время обновления статуса платежа",
        ),
        sa.Column(
            "processed_at", sa.DateTime(), nullable=True, comment="Дата и время финальной обработки платежа (UTC)"
        ),
        sa.Column(
            "webhook_send_at", sa.DateTime(), nullable=True, comment="Дата и время финальной обработки платежа (UTC)"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
        comment="Таблица информации о платежах",
    )


def downgrade() -> None:
    op.drop_table("payments")
    op.drop_table("outbox")
