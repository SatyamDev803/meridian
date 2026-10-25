"""Client-side mirror of Delta's rate limit so we slow down before the exchange makes us.

Delta allows 20,000 weight units per fixed 5-minute window. Reads cost 3, single order
operations 5, batch operations 25. Cancels are exempt. We budget only a share of the quota
so a burst of requotes can never lock us out of cancelling.
"""

from __future__ import annotations

import time
from collections.abc import Callable

WINDOW_S = 300.0
QUOTA = 20_000

WEIGHT_READ = 3
WEIGHT_ORDER = 5
WEIGHT_BATCH = 25
WEIGHT_FILLS = 10
WEIGHT_CANCEL = 0


class RateBudget:
    def __init__(
        self,
        quota: int = QUOTA,
        window_s: float = WINDOW_S,
        budget_share: float = 0.8,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = int(quota * budget_share)
        self.window_s = window_s
        self.clock = clock
        self.window_start = clock()
        self.used = 0
        self.blocked_until = 0.0

    def _roll(self) -> None:
        now = self.clock()
        if now - self.window_start >= self.window_s:
            self.window_start = now
            self.used = 0

    def try_spend(self, weight: int) -> bool:
        self._roll()
        if self.clock() < self.blocked_until:
            return weight == 0
        if self.used + weight > self.limit:
            return weight == 0
        self.used += weight
        return True

    def on_429(self, reset_ms: int | None) -> None:
        wait = (reset_ms or 10_000) / 1000
        self.blocked_until = self.clock() + wait

    @property
    def ok(self) -> bool:
        self._roll()
        headroom = self.used < self.limit * 0.95
        return headroom and self.clock() >= self.blocked_until

    def detail(self) -> str:
        self._roll()
        if self.clock() < self.blocked_until:
            return f"exchange asked us to wait {self.blocked_until - self.clock():.0f}s"
        return f"{self.used:,} of {self.limit:,} units used this window"

    def snapshot(self) -> dict:
        self._roll()
        return {
            "used": self.used,
            "limit": self.limit,
            "window_resets_in_s": round(self.window_s - (self.clock() - self.window_start), 1),
        }
