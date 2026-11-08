from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import pytest

from app.models import Event, Outbox, Payment, PaymentStatus
from app.repository import OutboxRepository, PaymentRepository
from app.services._dto import PaymentDtoDB
from app.services.exceptions import IdempotencyConflict, PaymentNotFound
from app.services.payment import PaymentService
from tests.test_01_functional.fakes import (
    IDEM_KEY,
    NOW,
    PAYMENT_ID,
    mk_payment,
    mk_request_body,
)


class FakePaymentRepository:
    def __init__(
        self, create_result: Payment | None = None, existing: Payment | None = None, get_result: Payment | None = None
    ) -> None:
        self._create_result = create_result
        self._existing = existing
        self._get_result = get_result
        self._create_kwargs: dict[str, Any] | None = None

    async def create_if_not_exists(self, **kwargs: Any) -> Payment | None:
        self._create_kwargs = kwargs
        return self._create_result

    async def get_by_idempotency_key(self, idempotency_key: str) -> Payment | None:
        return self._existing

    async def get_by_id(self, id: UUID) -> Payment | None:
        return self._get_result


class FakeOutboxRepository:
    def __init__(self) -> None:
        self._create_kwargs: dict[str, Any] | None = None

    async def create(self, **kwargs: Any) -> Outbox:
        self._create_kwargs = kwargs
        return Outbox(
            id=1,
            event_type=kwargs["event_type"],
            payload=kwargs["payload"],
            is_processed=False,
            created_at=NOW,
            processed_at=None,
        )


def mk_service(payment_repo: FakePaymentRepository) -> PaymentService:
    service = PaymentService()
    service.payment_repo = cast(PaymentRepository, payment_repo)
    service.outbox_repo = cast(OutboxRepository, FakeOutboxRepository())
    return service


good_new = mk_service(FakePaymentRepository(create_result=mk_payment()))

good_replay = mk_service(FakePaymentRepository(existing=mk_payment()))

good_replay_normalized = mk_service(
    FakePaymentRepository(existing=mk_payment(metadata_={"order_id": "1", "user": "u"}))
)

bad_amount = mk_service(FakePaymentRepository(existing=mk_payment(amount=Decimal("999.00"))))
bad_currency = mk_service(FakePaymentRepository(existing=mk_payment(currency="USD")))
bad_description = mk_service(FakePaymentRepository(existing=mk_payment(description="Другое")))
bad_metadata = mk_service(FakePaymentRepository(existing=mk_payment(metadata_={"order_id": "2"})))
bad_webhook = mk_service(FakePaymentRepository(existing=mk_payment(webhook_url="https://webhook.test/other")))


@pytest.mark.parametrize(
    "service, body, created, error",
    (
        (good_new, mk_request_body(), True, None),
        (good_replay, mk_request_body(), False, None),
        (good_replay_normalized, mk_request_body(amount="100.5", metadata={"user": "u", "order_id": "1"}), False, None),
        (bad_amount, mk_request_body(), False, IdempotencyConflict),
        (bad_currency, mk_request_body(), False, IdempotencyConflict),
        (bad_description, mk_request_body(), False, IdempotencyConflict),
        (bad_metadata, mk_request_body(), False, IdempotencyConflict),
        (bad_webhook, mk_request_body(), False, IdempotencyConflict),
    ),
)
async def test_create_payment(
    service: PaymentService,
    body: dict[str, Any],
    created: bool,
    error: type[Exception] | None,
) -> None:
    payment_repo = cast(FakePaymentRepository, service.payment_repo)
    outbox_repo = cast(FakeOutboxRepository, service.outbox_repo)

    if error is not None:
        with pytest.raises(error) as ex:
            await service.create(IDEM_KEY, body)

        assert IDEM_KEY in str(ex.value), f"Текст ошибки должен содержать ключ {IDEM_KEY=}, а не {ex.value}"
        assert outbox_repo._create_kwargs is None, (
            "При конфликте идемпотентности событие в outbox создаваться не должно"
        )
        return

    result = await service.create(IDEM_KEY, body)

    assert result.id == PAYMENT_ID, f"Сервис должен вернуть платеж {PAYMENT_ID=}, а вернул {result.id=}"
    assert payment_repo._create_kwargs is not None, "В репозиторий должны быть переданы данные платежа"
    assert payment_repo._create_kwargs["idempotency_key"] == IDEM_KEY, (
        "В репозиторий должен быть передан Idempotency-Key"
    )
    assert payment_repo._create_kwargs["status"] == PaymentStatus.PENDING, (
        "Новый платеж должен создаваться в статусе pending"
    )

    if created:
        assert outbox_repo._create_kwargs == {
            "event_type": Event.PAYMENT_CREATED.value,
            "payload": {"payment_id": str(PAYMENT_ID)},
        }, f"В outbox должно быть записано событие payment.created, а записано {outbox_repo._create_kwargs=}"
    else:
        assert outbox_repo._create_kwargs is None, "При повторе запроса новое событие в outbox создаваться не должно"


@pytest.mark.parametrize(
    "service, error",
    (
        (mk_service(FakePaymentRepository(get_result=mk_payment())), None),
        (mk_service(FakePaymentRepository(get_result=None)), PaymentNotFound),
    ),
)
async def test_get_payment(service: PaymentService, error: type[Exception] | None) -> None:
    if error is not None:
        with pytest.raises(error) as ex:
            await service.get(PAYMENT_ID)
        assert str(ex.value) == f"Payment {PAYMENT_ID} not found", f"Неверный текст ошибки {ex.value}"
        return

    result = await service.get(PAYMENT_ID)
    assert isinstance(result, PaymentDtoDB), f"Сервис должен вернуть {PaymentDtoDB.__name__}, а не {type(result)}"
    assert result.id == PAYMENT_ID, f"Сервис должен вернуть платеж {PAYMENT_ID=}, а вернул {result.id=}"
