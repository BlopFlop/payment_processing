import random

from typing import cast

import pytest

from app.services._dto import PaymentDtoDB
from app.services.gateway import GatewayMock
from tests.test_01_functional.fakes import mk_payment


class FakeRandom:
    def __init__(self, random_value: float) -> None:
        self._random_value = random_value
        self.uniform_args: tuple[float, float] | None = None

    def uniform(self, a: float, b: float) -> float:
        self.uniform_args = (a, b)
        return 0.0

    def random(self) -> float:
        return self._random_value


@pytest.mark.parametrize(
    "random_value, success_rate, expected",
    (
        (0.0, 0.9, True),
        (0.899, 0.9, True),
        (0.9, 0.9, False),
        (0.99, 0.9, False),
        (0.999, 1.0, True),
        (0.0, 0.0, False),
    ),
)
async def test_gateway_mock(random_value: float, success_rate: float, expected: bool) -> None:
    rng = FakeRandom(random_value)
    gateway = GatewayMock(success_rate=success_rate, rng=cast(random.Random, rng))

    result = await gateway.charge(PaymentDtoDB.from_orm(mk_payment()))

    assert result is expected, (
        f"При random={random_value} и success_rate={success_rate} результат должен быть {expected}"
    )
    assert rng.uniform_args == (2.0, 5.0), f"Задержка шлюза должна быть 2-5 сек, а не {rng.uniform_args}"
