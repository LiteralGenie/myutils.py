import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from queue import Queue
from typing import Any, Callable, Iterable, TypeVar, overload


@dataclass(kw_only=True)
class RateLimiter:
    max_requests: int = 3
    max_requests_period: float = 5

    _active: set[asyncio.Event] = field(default_factory=set)
    _cooldowns: dict[asyncio.Event, asyncio.Task] = field(default_factory=dict)
    _queue: Queue[asyncio.Event] = field(default_factory=Queue)

    @asynccontextmanager
    async def acquire(self):
        # Create ticket
        ticket = asyncio.Event()
        self._queue.put(ticket)
        self._consume_queue()
        await ticket.wait()

        try:
            # Yield to caller
            # fmt: off
            is_cancelled = False
            def cancel():
                nonlocal is_cancelled
                is_cancelled = True
            yield cancel
            # fmt: on
        finally:
            # Any tickets in cooldown count against rate limit
            # So if caller says nvm, avoid cd penalty
            if not is_cancelled:
                self._start_cooldown(ticket)

            # Cleanup
            self._active.remove(ticket)
            self._consume_queue()

    # Call this on any ticket CRUD
    # This checks if we are under the rate limit and pops / unblocks a queued ticket
    def _consume_queue(self):
        if len(self._cooldowns) + len(self._active) >= self.max_requests:
            return

        if self._queue.qsize() == 0:
            return

        ticket = self._queue.get()
        ticket.set()
        self._active.add(ticket)

    # Basically treat a rate limiter with N reqs per T seconds
    # as N individual rate limiters capped to 1 req per T seconds
    def _start_cooldown(self, ticket: asyncio.Event):
        async def cd():
            await asyncio.sleep(self.max_requests_period)

            del self._cooldowns[ticket]

            self._consume_queue()

        self._cooldowns[ticket] = asyncio.create_task(cd())


class DebugTimer:
    def __init__(
        self,
        format=".2f",
        reset_on_read=False,
    ):
        self.start = time.time()
        self.format = format
        self.reset_on_read = reset_on_read

    def reset(self):
        self.start = time.time()
        return self

    @property
    def elapsed(self):
        return time.time() - self.start

    @property
    def t(self):
        return f"{self.elapsed:{self.format}}"

    def tr(self):
        t = self.t
        self.reset()
        return t

    def __str__(self):
        elapsed_str = self.t

        if self.reset_on_read:
            self.reset()

        return elapsed_str


T = TypeVar("T")
U = TypeVar("U")


# fmt:off
@overload
def nn_(x: T | None) -> T: ...
# These 2-arg overloads don't actually work in extracting T from T|U ...
@overload
def nn_(x: T | U, check: Callable[[T | U], bool]) -> Any: ...
@overload
def nn_(x: T | U, check: U) -> T: ...
# @overload
# def nn_(x: T | U, check: Callable[[T | None], T]) -> T: ...
@overload
def nn_(x: T | U, check: Callable[[T | U], bool] | U, cast_to: type[T]) -> T: ...
# fmt:on


def nn_(
    x,
    check=None,
    type_=None,
) -> T | U:
    if callable(check):
        result = check(x)
        if isinstance(result, bool) and result:
            raise ValueError(f"{x!r} invalid (fails {check!r})")
        elif result is None:
            raise ValueError(f"{x!r} invalid (fails {check!r})")
    else:
        if x == check:
            raise ValueError(f"{x!r} invalid (equals {check!r})")

    return x


def filter_none(xs: Iterable[T | None]) -> Any:
    return (x for x in xs if x is not None)
