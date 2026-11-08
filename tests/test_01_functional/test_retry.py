from typing import Any, cast

import pytest

from faststream.rabbit import RabbitBroker

from app.core.broker import (
    ATTEMPT_HEADER,
    DLQ_ROUTING_KEY,
    DLX_EXCHANGE,
    ERROR_HEADER,
    NEW_ROUTING_KEY,
    PAYMENTS_EXCHANGE,
    build_retry_queues,
)
from app.services.retry import Retry
from tests.test_01_functional.fakes import PAYMENT_ID, FakeBroker


RETRY_QUEUES = build_retry_queues(max_attempts=3, base_delay=1.0)
LONG_ERROR = RuntimeError("x" * 2000)


@pytest.mark.parametrize(
    "attempt, error, expected_queue, expected_header",
    (
        (0, RuntimeError("boom"), "payments.retry.0", 1),
        (1, RuntimeError("boom"), "payments.retry.1", 2),
        (2, RuntimeError("boom"), None, 3),
        (7, RuntimeError("boom"), None, 8),
        (0, LONG_ERROR, "payments.retry.0", 1),
    ),
)
async def test_retry_schedule(attempt: int, error: Exception, expected_queue: str | None, expected_header: int) -> None:
    broker = FakeBroker()
    retry = Retry(cast(RabbitBroker, broker), RETRY_QUEUES)
    body = {"payment_id": str(PAYMENT_ID), "event_id": 1}

    await retry.schedule(body, attempt, error)

    assert retry.max_attempts == 3, f"Всего попыток должно быть 3, а не {retry.max_attempts}"
    assert len(broker.published) == 1, f"Должна быть одна публикация, а было {len(broker.published)}"

    published = broker.published[0]
    assert published["message"] == body, "Тело сообщения должно сохраняться без изменений"
    assert published["persist"] is True, "Сообщение должно публиковаться как persistent"
    assert published["headers"][ATTEMPT_HEADER] == expected_header, (
        f"Заголовок {ATTEMPT_HEADER} должен быть {expected_header}, а не {published['headers'][ATTEMPT_HEADER]}"
    )
    error_header = published["headers"][ERROR_HEADER]
    assert error_header.startswith("RuntimeError: "), (
        f"В {ERROR_HEADER} должен быть тип ошибки, а не {error_header[:50]}"
    )
    assert len(error_header) <= 500, f"{ERROR_HEADER} должен обрезаться до 500 символов, а не {len(error_header)}"

    if expected_queue is not None:
        assert published["queue"].name == expected_queue, (
            f"Сообщение должно уйти в {expected_queue}, а ушло в {published['queue']}"
        )
    else:
        assert published["exchange"] == DLX_EXCHANGE, "После исчерпания попыток сообщение должно уйти в DLX"
        assert published["routing_key"] == DLQ_ROUTING_KEY, f"Routing key DLQ должен быть {DLQ_ROUTING_KEY}"


@pytest.mark.parametrize(
    "headers, expected",
    (
        (None, 0),
        ({}, 0),
        ({ATTEMPT_HEADER: 2}, 2),
        ({ATTEMPT_HEADER: "3"}, 3),
        ({ATTEMPT_HEADER: "bad"}, 0),
        ({ATTEMPT_HEADER: None}, 0),
    ),
)
def test_attempt_from_headers(headers: dict[str, Any] | None, expected: int) -> None:
    result = Retry.attempt_from_headers(headers)
    assert result == expected, f"Для заголовков {headers=} номер попытки должен быть {expected}, а не {result}"


@pytest.mark.parametrize(
    "max_attempts, base_delay, expected_ttls",
    (
        (3, 1.0, [1000, 2000]),
        (4, 0.5, [500, 1000, 2000]),
        (1, 1.0, []),
        (0, 1.0, []),
    ),
)
def test_build_retry_queues(max_attempts: int, base_delay: float, expected_ttls: list[int]) -> None:
    queues = build_retry_queues(max_attempts, base_delay)

    assert [q.arguments["x-message-ttl"] for q in queues] == expected_ttls, (
        f"TTL retry-очередей должны расти экспоненциально: {expected_ttls}"
    )
    assert [q.name for q in queues] == [f"payments.retry.{i}" for i in range(len(expected_ttls))], (
        "Неверные имена очередей"
    )
    for queue in queues:
        assert queue.arguments["x-dead-letter-exchange"] == PAYMENTS_EXCHANGE.name, (
            "По истечении TTL сообщение должно возвращаться в exchange payments"
        )
        assert queue.arguments["x-dead-letter-routing-key"] == NEW_ROUTING_KEY, "...и попадать в payments.new"
