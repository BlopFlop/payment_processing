import random
import asyncio

from abc import ABC, abstractmethod

from ._dto import PaymentDtoDB


class Gateway(ABC):
    @abstractmethod
    async def charge(self, payment: PaymentDtoDB) -> bool:
        pass


class GatewayMock(Gateway):
    def __init__(
        self,
        min_delay: float = 2.0,
        max_delay: float = 5.0,
        success_rate: float = 0.9,
        rng: random.Random | None = None,
    ) -> None:
        self._min_delay = min_delay
        self._max_delay = max_delay
        self._success_rate = success_rate
        self._rng = rng or random.Random()

    async def charge(self, payment: PaymentDtoDB) -> bool:
        await asyncio.sleep(self._rng.uniform(self._min_delay, self._max_delay))
        return self._rng.random() < self._success_rate
