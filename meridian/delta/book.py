"""Local order book maintained from Delta's `ob_updates` channel.

Protocol (docs.delta.exchange, "ob_updates"):
  1. The first message has action "snapshot" with full asks "a" and bids "b".
  2. Later messages have action "update". Each level is [price, new_size]; size "0" deletes it.
  3. "seq" must be exactly previous + 1. On a gap we must resubscribe.
  4. "cs" is CRC32 of "p0:s0,...,p9:s9|p0:s0,...,p9:s9" over the top 10 asks (ascending)
     then top 10 bids (descending), using the price and size strings as the exchange sent them.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from decimal import Decimal

CHECKSUM_LEVELS = 10


class BookError(Exception):
    """The local book can no longer be trusted. The caller must resubscribe."""


class SequenceGap(BookError):
    pass


class ChecksumMismatch(BookError):
    pass


@dataclass
class Level:
    price: str
    size: str


@dataclass
class ObUpdatesBook:
    symbol: str
    bids: dict[Decimal, Level] = field(default_factory=dict)
    asks: dict[Decimal, Level] = field(default_factory=dict)
    seq: int | None = None
    synced: bool = False
    last_update_us: int = 0
    checksum_failures: int = 0

    def reset(self) -> None:
        self.bids.clear()
        self.asks.clear()
        self.seq = None
        self.synced = False

    def on_message(self, msg: dict, *, verify_checksum: bool = True) -> None:
        action = msg.get("action")
        if action == "error":
            self.reset()
            raise BookError(msg.get("msg", "ob_updates error"))
        if action == "snapshot":
            self.reset()
            self._apply_levels(self.asks, msg.get("a", []))
            self._apply_levels(self.bids, msg.get("b", []))
            self.seq = int(msg["seq"])
        elif action == "update":
            if not self.synced or self.seq is None:
                return  # still waiting for a snapshot
            seq = int(msg["seq"])
            expected = self.seq + 1
            if seq != expected:
                self.reset()
                raise SequenceGap(f"expected seq {expected}, got {seq}")
            self._apply_levels(self.asks, msg.get("a", []))
            self._apply_levels(self.bids, msg.get("b", []))
            self.seq = seq
        else:
            return
        self.last_update_us = int(msg.get("ts", 0))
        self.synced = True
        if verify_checksum and "cs" in msg and int(msg["cs"]) != self.checksum():
            self.checksum_failures += 1
            self.reset()
            raise ChecksumMismatch(f"checksum mismatch at seq {msg.get('seq')}")

    @staticmethod
    def _apply_levels(side: dict[Decimal, Level], levels: list[list[str]]) -> None:
        for price_s, size_s in levels:
            price = Decimal(str(price_s))
            if Decimal(str(size_s)) == 0:
                side.pop(price, None)
            else:
                side[price] = Level(str(price_s), str(size_s))

    def sorted_asks(self, depth: int | None = None) -> list[Level]:
        keys = sorted(self.asks)[:depth] if depth else sorted(self.asks)
        return [self.asks[k] for k in keys]

    def sorted_bids(self, depth: int | None = None) -> list[Level]:
        keys = sorted(self.bids, reverse=True)
        keys = keys[:depth] if depth else keys
        return [self.bids[k] for k in keys]

    def checksum_string(self) -> str:
        asks = ",".join(f"{lv.price}:{lv.size}" for lv in self.sorted_asks(CHECKSUM_LEVELS))
        bids = ",".join(f"{lv.price}:{lv.size}" for lv in self.sorted_bids(CHECKSUM_LEVELS))
        return f"{asks}|{bids}"

    def checksum(self) -> int:
        return zlib.crc32(self.checksum_string().encode()) & 0xFFFFFFFF

    def best_bid(self) -> Decimal | None:
        return max(self.bids) if self.bids else None

    def best_ask(self) -> Decimal | None:
        return min(self.asks) if self.asks else None

    def mid(self) -> Decimal | None:
        bid, ask = self.best_bid(), self.best_ask()
        if bid is None or ask is None:
            return None
        return (bid + ask) / 2

    def crossed(self) -> bool:
        bid, ask = self.best_bid(), self.best_ask()
        return bid is not None and ask is not None and bid >= ask

    def depth(self, levels: int = 10) -> dict[str, list[list[str]]]:
        return {
            "bids": [[lv.price, lv.size] for lv in self.sorted_bids(levels)],
            "asks": [[lv.price, lv.size] for lv in self.sorted_asks(levels)],
        }
