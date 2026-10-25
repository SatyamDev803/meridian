"""Binance best bid/offer as an independent reference price.

`<symbol>@bookTicker` pushes every change to the top of book, so we need no snapshot or
diff bookkeeping: each message is the full answer. Public, no API key.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from decimal import Decimal

import websockets
from websockets.asyncio.client import connect

from meridian.delta.ws import backoff_delay

log = logging.getLogger("meridian.binance")


class BinanceRefFeed:
    def __init__(
        self,
        ws_base: str,
        symbol: str,
        on_quote: Callable[[Decimal, Decimal], None],
        on_state: Callable[[str, str], None] | None = None,
    ) -> None:
        self.url = f"{ws_base.rstrip('/')}/{symbol.lower()}@bookTicker"
        self.on_quote = on_quote
        self.on_state = on_state or (lambda s, d: None)
        self.connected = False
        self.last_message_at: float | None = None
        self.messages = 0
        self.reconnects = 0
        self.paused_until = 0.0  # chaos hook: ignore messages until then
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        attempt = 0
        while not self._stop.is_set():
            try:
                async with connect(self.url, ping_interval=20, ping_timeout=10) as ws:
                    self.connected = True
                    attempt = 0
                    self.on_state("connected", self.url)
                    async for raw in ws:
                        if time.monotonic() < self.paused_until:
                            continue
                        msg = json.loads(raw)
                        if "b" not in msg or "a" not in msg:
                            continue
                        self.last_message_at = time.monotonic()
                        self.messages += 1
                        self.on_quote(Decimal(msg["b"]), Decimal(msg["a"]))
            except asyncio.CancelledError:
                raise
            except (OSError, websockets.WebSocketException, TimeoutError, ValueError) as exc:
                log.warning("binance: %r", exc)
            except Exception:
                log.exception("binance: unexpected error")
            finally:
                self.connected = False
            if self._stop.is_set():
                break
            delay = backoff_delay(attempt)
            attempt += 1
            self.reconnects += 1
            self.on_state("disconnected", f"retrying in {delay:.1f}s")
            await asyncio.sleep(delay)
