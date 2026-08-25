"""Bounded in-process sliding-window rate limiting."""

import asyncio
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


class SlidingWindowLimiter:
    def __init__(self, max_keys: int = 10_000) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()
        self._max_keys = max_keys
        self._last_cleanup = 0.0

    def _cleanup(self, now: float, window_seconds: float) -> None:
        if now - self._last_cleanup < window_seconds and len(self._events) <= self._max_keys:
            return
        cutoff = now - window_seconds
        expired = [
            key for key, events in self._events.items() if not events or events[-1] <= cutoff
        ]
        for key in expired:
            self._events.pop(key, None)
        if len(self._events) > self._max_keys:
            oldest = sorted(
                self._events,
                key=lambda key: self._events[key][-1] if self._events[key] else float("-inf"),
            )[: len(self._events) - self._max_keys]
            for key in oldest:
                self._events.pop(key, None)
        self._last_cleanup = now

    async def enforce(self, request: Request, scope: str, limit: int, window_seconds: float = 60.0) -> None:
        host = request.client.host if request.client else "unknown"
        key = f"{scope}:{host}"
        now = time.monotonic()
        async with self._lock:
            self._cleanup(now, window_seconds)
            events = self._events[key]
            while events and events[0] <= now - window_seconds:
                events.popleft()
            if len(events) >= limit:
                retry_after = max(1, int(window_seconds - (now - events[0])))
                raise HTTPException(
                    status_code=429,
                    detail={"code": "rate_limit_exceeded", "message": "Too many requests", "retry_after_seconds": retry_after},
                    headers={"Retry-After": str(retry_after)},
                )
            events.append(now)


limiter = SlidingWindowLimiter()
