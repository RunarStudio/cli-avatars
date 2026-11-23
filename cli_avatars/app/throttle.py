"""Store reads from the tick stay at two per second or fewer."""

import time
from typing import Callable, TypeVar

T = TypeVar("T")

#: Minimum gap between decision and topic reads. Two reads a second.
READ_INTERVAL_S = 0.5


class StoreThrottle:
    """Return a cached loader result until ``interval`` seconds have passed."""

    def __init__(self, interval: float = READ_INTERVAL_S) -> None:
        self.interval = interval
        self._next = 0.0
        self._value: object = None
        self._ready = False

    def due(self, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        return now >= self._next

    def mark(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        self._next = now + self.interval

    def get(self, loader: Callable[[], T], now: float | None = None) -> T:
        now = time.monotonic() if now is None else now
        if self._ready and now < self._next:
            return self._value  # type: ignore[return-value]
        value = loader()
        self._value = value
        self._ready = True
        self._next = now + self.interval
        return value
