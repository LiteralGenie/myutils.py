from dataclasses import dataclass, field
from contextlib import asynccontextmanager
import asyncio
import time


@dataclass(kw_only=True)
class RateLimiter:
    max_requests: int = 3
    max_requests_period: float = 5
    sem: asyncio.Semaphore = field(init=False)
    times: list[float] = field(default_factory=list)
    req_count: int = 0

    def __post_init__(self):
        self.sem = asyncio.Semaphore(self.max_requests)

    @asynccontextmanager
    async def acquire(self):
        async with self.sem:
            req_count = self.req_count
            self.req_count += 1

            if req_count >= self.max_requests:
                oldest_time = self.times.pop(0)
                rem_delay = self.max_requests_period - (time.time() - oldest_time)
                if rem_delay > 0:
                    await asyncio.sleep(rem_delay)

            is_cancelled = False

            def cancel():
                nonlocal is_cancelled
                is_cancelled = True

            yield cancel

            if not is_cancelled:
                self.times.append(time.time())
            else:
                self.req_count -= 1
