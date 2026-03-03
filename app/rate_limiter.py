from __future__ import annotations

import asyncio
from collections import deque
from time import monotonic


class OperationRateLimiter:
    def __init__(self, *, limit: int, window_s: float) -> None:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        if window_s <= 0:
            raise ValueError("window_s must be greater than zero")

        self._limit = limit
        self._window_s = window_s
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            sleep_for = 0.0
            async with self._lock:
                now = monotonic()
                self._trim(now)
                if len(self._timestamps) < self._limit:
                    self._timestamps.append(now)
                    return

                sleep_for = self._window_s - (now - self._timestamps[0])

            await asyncio.sleep(max(sleep_for, 0.05))

    def _trim(self, now: float) -> None:
        while self._timestamps and now - self._timestamps[0] >= self._window_s:
            self._timestamps.popleft()


__all__ = ["OperationRateLimiter"]
