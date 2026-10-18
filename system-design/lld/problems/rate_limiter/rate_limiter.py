"""Rate Limiter - LLD. Pattern: Strategy (pluggable algorithms). Thread-safe, single process.

For the multi-server version (shared counters in Redis) see hld/case-studies/rate-limiter.md.
"""
from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from collections import defaultdict, deque


class RateLimiter(ABC):
    @abstractmethod
    def allow(self, client_id: str) -> bool:
        """Return True if this request is allowed, False if it should get HTTP 429."""


class TokenBucketLimiter(RateLimiter):
    """Bucket holds up to `capacity` tokens and refills at `refill_per_sec`.
    Each request costs one token. Allows bursts up to `capacity`."""

    def __init__(self, capacity: int, refill_per_sec: float):
        self.capacity, self.rate = capacity, refill_per_sec
        self.buckets: dict[str, tuple[float, float]] = {}  # client -> (tokens, last_refill_time)
        self._lock = threading.Lock()

    def allow(self, client_id):
        now = time.monotonic()
        with self._lock:
            tokens, last = self.buckets.get(client_id, (self.capacity, now))  # new client: full bucket
            # Lazy refill: add the tokens earned since the last call (no background thread needed).
            tokens = min(self.capacity, tokens + (now - last) * self.rate)
            allowed = tokens >= 1
            if allowed:
                tokens -= 1
            self.buckets[client_id] = (tokens, now)
            return allowed


class FixedWindowLimiter(RateLimiter):
    """At most `limit` requests per fixed, back-to-back window of `window_sec` seconds.
    Simple and cheap, but allows up to 2x `limit` around a window boundary."""

    def __init__(self, limit: int, window_sec: float):
        self.limit, self.window = limit, window_sec
        self.state: dict[str, tuple[int, int]] = {}  # client -> (window_id, count): O(1) memory per client
        self._lock = threading.Lock()

    def allow(self, client_id):
        window_id = int(time.monotonic() // self.window)
        with self._lock:
            current_window, count = self.state.get(client_id, (window_id, 0))
            if current_window != window_id:  # a new window started: reset the counter
                count = 0
            if count < self.limit:
                self.state[client_id] = (window_id, count + 1)
                return True
            self.state[client_id] = (window_id, count)
            return False


class SlidingWindowLogLimiter(RateLimiter):
    """Exact: keeps the timestamp of each allowed request in the last `window_sec`.
    Memory is O(limit) per client."""

    def __init__(self, limit: int, window_sec: float):
        self.limit, self.window = limit, window_sec
        self.logs: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, client_id):
        now = time.monotonic()
        with self._lock:
            log = self.logs[client_id]
            while log and log[0] <= now - self.window:  # drop timestamps that left the window
                log.popleft()
            if len(log) < self.limit:
                log.append(now)  # only ALLOWED requests are logged
                return True
            return False


class SlidingWindowCounterLimiter(RateLimiter):
    """Approximation: weight the previous window's count by how much of it still overlaps
    the sliding window. O(1) memory per client, smooths the fixed-window boundary burst."""

    def __init__(self, limit: int, window_sec: float):
        self.limit, self.window = limit, window_sec
        self.state: dict[str, tuple[int, int, int]] = {}  # client -> (window_id, current_count, previous_count)
        self._lock = threading.Lock()

    def allow(self, client_id):
        now = time.monotonic()
        window_id = int(now // self.window)
        elapsed_fraction = (now % self.window) / self.window  # how far we are into the current window
        with self._lock:
            wid, curr, prev = self.state.get(client_id, (window_id, 0, 0))
            if window_id == wid + 1:      # moved into the next window
                wid, curr, prev = window_id, 0, curr
            elif window_id > wid + 1:     # idle for more than a whole window
                wid, curr, prev = window_id, 0, 0
            estimated = prev * (1 - elapsed_fraction) + curr
            if estimated < self.limit:
                self.state[client_id] = (wid, curr + 1, prev)
                return True
            self.state[client_id] = (wid, curr, prev)
            return False


if __name__ == "__main__":
    limiters = (
        TokenBucketLimiter(capacity=3, refill_per_sec=1),
        FixedWindowLimiter(limit=3, window_sec=3600),
        SlidingWindowLogLimiter(limit=3, window_sec=1),
        SlidingWindowCounterLimiter(limit=3, window_sec=3600),
    )
    for limiter in limiters:
        burst = ["Y" if limiter.allow("user1") else "N" for _ in range(5)]
        print(f"{type(limiter).__name__:<28} burst of 5: {' '.join(burst)}")

    tb = TokenBucketLimiter(capacity=3, refill_per_sec=10)
    for _ in range(3):
        tb.allow("u")
    print("token bucket empty ->", tb.allow("u"))
    time.sleep(0.25)  # ~2.5 tokens refill
    print("after 0.25s        ->", tb.allow("u"), tb.allow("u"), tb.allow("u"))

    sw = SlidingWindowLogLimiter(limit=2, window_sec=0.2)
    print("sliding log        ->", sw.allow("u"), sw.allow("u"), sw.allow("u"))
    time.sleep(0.21)
    print("after window       ->", sw.allow("u"))

    # Thread safety: 50 threads x 10 requests against a limit of 100 per window -> exactly 100 allowed.
    fw = FixedWindowLimiter(limit=100, window_sec=3600)
    allowed = []

    def hammer():
        for _ in range(10):
            if fw.allow("shared"):
                allowed.append(1)

    threads = [threading.Thread(target=hammer) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print("concurrent allowed ->", len(allowed), "(expected 100)")
