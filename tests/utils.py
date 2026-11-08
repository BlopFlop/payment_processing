import asyncio

from collections.abc import Awaitable, Callable


async def wait_for[T](
    predicate: Callable[[], Awaitable[T | None]],
    message: str,
    timeout: float = 15.0,
    interval: float = 0.05,
) -> T:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        result = await predicate()
        if result:
            return result
        if loop.time() > deadline:
            raise AssertionError(f"{message} (не дождались за {timeout} c)")
        await asyncio.sleep(interval)
