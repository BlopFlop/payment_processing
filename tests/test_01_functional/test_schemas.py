from typing import Any

from pydantic import BaseModel, ValidationError

import pytest

from app.api.schemas import (
    IdempotencyConflictError,
    PaymentNotFoundError,
    UnauthorizedError,
)
from app.api.v1.schemas import CreatePaymentRequest
from tests.fixtures.payments import payment_body


@pytest.mark.parametrize(
    "overrides, removed",
    (
        ({"amount": "0.01"}, None),
        ({"amount": "100"}, None),
        ({"currency": "USD"}, None),
        ({"currency": "EUR"}, None),
        ({"description": None}, None),
        ({}, "description"),
        ({}, "metadata"),
    ),
)
def test_create_request_valid(overrides: dict[str, Any], removed: str | None) -> None:
    body = payment_body(**overrides)
    if removed:
        body.pop(removed)

    request = CreatePaymentRequest(**body)
    if removed == "metadata":
        assert request.metadata == {}, "metadata по умолчанию должна быть пустым словарём"


@pytest.mark.parametrize(
    "overrides, removed, error_type, loc",
    (
        ({"amount": "0"}, None, "greater_than", ("amount",)),
        ({"amount": "-5"}, None, "greater_than", ("amount",)),
        ({"amount": "1.001"}, None, "decimal_max_places", ("amount",)),
        ({"amount": "abc"}, None, "decimal_parsing", ("amount",)),
        ({"currency": "GBP"}, None, "enum", ("currency",)),
        ({"currency": "rub"}, None, "enum", ("currency",)),
        ({"webhook_url": "not-url"}, None, "url_parsing", ("webhook_url",)),
        ({"webhook_url": "ftp://webhook.test"}, None, "url_scheme", ("webhook_url",)),
        ({"description": "x" * 1025}, None, "string_too_long", ("description",)),
        ({"foo": "bar"}, None, "extra_forbidden", ("foo",)),
        ({}, "webhook_url", "missing", ("webhook_url",)),
        ({}, "amount", "missing", ("amount",)),
        ({}, "currency", "missing", ("currency",)),
    ),
)
def test_create_request_invalid(
    overrides: dict[str, Any], removed: str | None, error_type: str, loc: tuple[str, ...]
) -> None:
    body = payment_body(**overrides)
    if removed:
        body.pop(removed)

    with pytest.raises(ValidationError) as ex:
        CreatePaymentRequest(**body)

    errors = [(e["type"], e["loc"]) for e in ex.value.errors()]
    assert (error_type, loc) in errors, f"Ожидалась ошибка {error_type} для поля {loc}, а получены {errors}"


@pytest.mark.parametrize("model", [UnauthorizedError, PaymentNotFoundError, IdempotencyConflictError])
def test_error_example(model: type[BaseModel]) -> None:
    examples = model.model_json_schema().get("examples")

    assert examples, f"У модели {model.__name__} должен быть пример для Swagger"
    for example in examples:
        model.model_validate(example)
