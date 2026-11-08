import uuid

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import DECIMAL, JSON, BigInteger, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = {"comment": "Таблица информации о платежах"}

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, comment="Уникальный идентификатор платежа в системе"
    )
    idempotency_key: Mapped[str] = mapped_column(
        unique=True, comment="Ключ идемпотентности для предотвращения дублирования транзакций"
    )
    status: Mapped[PaymentStatus] = mapped_column(comment="Текущий статус платежа")

    amount: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=18, scale=2), comment="Сумма платежа с фиксированной точностью"
    )
    currency: Mapped[str] = mapped_column(comment="Валюта платежа")
    description: Mapped[str | None] = mapped_column(comment="Назначение платежа или описание для пользователя")
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        JSON, comment="Дополнительные произвольные данные по платежу в формате JSON"
    )
    webhook_url: Mapped[str | None] = mapped_column(
        comment="Адрес для отправки асинхронного уведомления о финальном статусе"
    )
    created_at: Mapped[datetime] = mapped_column(server_default=text("NOW()"), comment="Дата и время создания платежа")
    status_updated: Mapped[datetime] = mapped_column(
        server_default=text("NOW()"), comment="Дата и время обновления статуса платежа"
    )
    processed_at: Mapped[datetime | None] = mapped_column(comment="Дата и время финальной обработки платежа (UTC)")
    webhook_send_at: Mapped[datetime | None] = mapped_column(comment="Дата и время финальной обработки платежа (UTC)")


class Event(StrEnum):
    PAYMENT_CREATED = "payment.created"
    PAYMENT_SUCCEEDED = "payment.succeeded"
    PAYMENT_FAILED = "payment.failed"


class Outbox(Base):
    __tablename__ = "outbox"
    __table_args__ = {"comment": "Таблица исходящих событий для реализации паттерна Transactional Outbox"}

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="Уникальный идентификатор события"
    )
    event_type: Mapped[Event] = mapped_column(comment="Тип бизнес-события (например: payment.succeeded)")
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON, comment="Тело сообщения (данные события) для отправки в брокер"
    )
    is_processed: Mapped[bool] = mapped_column(
        default=False, server_default=text("false"), comment="Флаг обработки события релеем / воркером отправки"
    )
    created_at: Mapped[datetime] = mapped_column(server_default=text("NOW()"), comment="Время генерации события")
    processed_at: Mapped[datetime | None] = mapped_column(comment="Время успешной отправки события в брокер сообщений")
