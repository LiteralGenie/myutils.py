import time
from queue import Queue
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
import asyncio


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

        # Yield to caller
        # fmt: off
        is_cancelled = False
        def cancel():
            nonlocal is_cancelled
            is_cancelled = True
        yield cancel
        # fmt: on

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
