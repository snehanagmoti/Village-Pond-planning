"""Small bounded in-process TTL cache for immutable upstream responses."""

import time
from collections import OrderedDict
from copy import deepcopy
from typing import Generic, Hashable, Optional, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    def __init__(self, maxsize: int = 128, ttl_seconds: int = 3600):
        self.maxsize = maxsize
        self.ttl_seconds = ttl_seconds
        self._items: OrderedDict[Hashable, tuple[float, T]] = OrderedDict()

    def get(self, key: Hashable) -> Optional[T]:
        item = self._items.get(key)
        if item is None:
            return None
        expires_at, value = item
        if expires_at < time.monotonic():
            self._items.pop(key, None)
            return None
        self._items.move_to_end(key)
        return deepcopy(value)

    def set(self, key: Hashable, value: T) -> None:
        if self.ttl_seconds <= 0:
            return
        self._items[key] = (time.monotonic() + self.ttl_seconds, deepcopy(value))
        self._items.move_to_end(key)
        while len(self._items) > self.maxsize:
            self._items.popitem(last=False)

    def clear(self) -> None:
        self._items.clear()
