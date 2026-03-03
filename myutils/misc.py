from queue import Queue
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
import asyncio


@dataclass(kw_only=True)
class RateLimiter:
    max_requests: int = 3
    max_requests_period: float = 5

    _cooldowns: dict[int, asyncio.Task] = field(default_factory=dict)
    _queue: Queue[dict] = field(default_factory=Queue)
    _nextTicketId: int = 0

    @asynccontextmanager
    async def acquire(self):
        ready_flag = asyncio.Event()
        ticket: dict = dict(
            id=self._nextTicketId,
            event=ready_flag,
        )
        self._nextTicketId += 1
        self._queue.put(ticket)

        self._consume_queue()
        await ready_flag.wait()

        is_cancelled = False

        def cancel():
            nonlocal is_cancelled
            is_cancelled = True

        yield cancel

        if not is_cancelled:
            self._start_cooldown(ticket["id"])
        else:
            self._consume_queue()

    def _consume_queue(self):
        if len(self._cooldowns) >= self.max_requests:
            return

        if self._queue.qsize() == 0:
            return

        ticket = self._queue.get()
        ticket["event"].set()

    def _start_cooldown(self, id: int):
        async def cd():
            await asyncio.sleep(self.max_requests_period)
            del self._cooldowns[id]

            self._consume_queue()

        self._cooldowns[id] = asyncio.create_task(cd())
