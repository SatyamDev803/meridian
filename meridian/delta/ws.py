"""Reconnecting WebSocket client for Delta's public and private endpoints.

On every connection:
  1. enable server heartbeats (Delta sends {"type": "heartbeat"} every 30 s),
  2. authenticate with key-auth if this is the private socket,
  3. subscribe to the configured channels.
A watchdog closes the socket if nothing arrives for `silence_s` (Delta recommends 35 s),
and the run loop reconnects with exponential backoff plus jitter.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection, connect

from meridian.delta.auth import ws_auth_message

log = logging.getLogger("meridian.ws")

Handler = Callable[[dict[str, Any]], Awaitable[None] | None]


def backoff_delay(attempt: int, base_s: float = 0.5, cap_s: float = 20.0) -> float:
    """Exponential backoff with +/-50% jitter, clamped to the cap (from FeedWatch)."""
    return min(cap_s, base_s * 2**attempt * random.uniform(0.5, 1.5))


class DeltaSocket:
    def __init__(
        self,
        name: str,
        url: str,
        channels: list[dict[str, Any]],
        on_message: Handler,
        *,
        api_key: str = "",
        api_secret: str = "",
        silence_s: float = 35.0,
        on_state: Callable[[str, str], None] | None = None,
    ) -> None:
        self.name = name
        self.url = url
        self.channels = channels
        self.on_message = on_message
        self.api_key = api_key
        self.api_secret = api_secret
        self.private = bool(api_key)
        self.silence_s = silence_s
        self.on_state = on_state or (lambda state, detail: None)

        self.connected = False
        self.authenticated = False
        self.last_message_at: float | None = None
        self.reconnects = 0
        self.messages = 0
        self._ws: ClientConnection | None = None
        self._stop = asyncio.Event()

    @property
    def ready(self) -> bool:
        return self.connected and (self.authenticated or not self.private)

    def silence(self, now: float | None = None) -> float | None:
        if self.last_message_at is None:
            return None
        return (now or time.monotonic()) - self.last_message_at

    async def send(self, msg: dict[str, Any]) -> None:
        if self._ws is not None:
            await self._ws.send(json.dumps(msg))

    async def resubscribe(self, channel: str, symbols: list[str]) -> None:
        """Used after an order book gap: unsubscribe then subscribe to get a fresh snapshot."""
        await self.send({"type": "unsubscribe", "payload": {"channels": [{"name": channel}]}})
        await self.send(
            {"type": "subscribe", "payload": {"channels": [{"name": channel, "symbols": symbols}]}}
        )

    async def force_reconnect(self, reason: str) -> None:
        log.warning("%s: forcing reconnect: %s", self.name, reason)
        if self._ws is not None:
            await self._ws.close(code=4000, reason=reason[:100])

    def stop(self) -> None:
        self._stop.set()
        if self._ws is not None:
            self._closing = asyncio.ensure_future(self._ws.close())

    async def run(self) -> None:
        attempt = 0
        while not self._stop.is_set():
            try:
                async with connect(
                    self.url, ping_interval=20, ping_timeout=10, open_timeout=10, max_size=2**22
                ) as ws:
                    self._ws = ws
                    self.connected = True
                    self.last_message_at = time.monotonic()
                    attempt = 0
                    self.on_state("connected", self.url)
                    await self._handshake(ws)
                    watchdog = asyncio.create_task(self._watchdog(ws))
                    try:
                        async for raw in ws:
                            self.last_message_at = time.monotonic()
                            self.messages += 1
                            await self._dispatch(raw)
                    finally:
                        watchdog.cancel()
            except asyncio.CancelledError:
                raise
            except (OSError, websockets.WebSocketException, TimeoutError) as exc:
                log.warning("%s: connection error: %r", self.name, exc)
            except Exception:
                log.exception("%s: unexpected error in socket loop", self.name)
            finally:
                self._ws = None
                was_connected = self.connected
                self.connected = False
                self.authenticated = False
            if self._stop.is_set():
                break
            delay = backoff_delay(attempt)
            attempt += 1
            self.reconnects += 1
            self.on_state(
                "disconnected", f"retrying in {delay:.1f}s" if was_connected else "retrying"
            )
            await asyncio.sleep(delay)

    async def _handshake(self, ws: ClientConnection) -> None:
        await ws.send(json.dumps({"type": "enable_heartbeat"}))
        if self.private:
            await ws.send(json.dumps(ws_auth_message(self.api_key, self.api_secret)))
        else:
            await self._subscribe(ws)

    async def _subscribe(self, ws: ClientConnection) -> None:
        if self.channels:
            await ws.send(json.dumps({"type": "subscribe", "payload": {"channels": self.channels}}))

    async def _dispatch(self, raw: str | bytes) -> None:
        try:
            msg = json.loads(raw)
        except ValueError:
            log.warning("%s: non-JSON frame dropped", self.name)
            return
        if not isinstance(msg, dict):
            return
        kind = msg.get("type")
        if kind == "heartbeat":
            return
        if kind == "key-auth":
            if msg.get("success"):
                self.authenticated = True
                self.on_state("authenticated", "key-auth ok")
                if self._ws is not None:
                    await self._subscribe(self._ws)
            else:
                self.on_state("auth_failed", str(msg.get("status") or msg.get("message")))
            return
        if kind == "subscriptions":
            errors = [c for c in msg.get("channels", []) if c.get("error")]
            for c in errors:
                self.on_state("subscribe_error", f"{c.get('name')}: {c.get('error')}")
            return
        try:
            result = self.on_message(msg)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            log.exception("%s: handler failed for %s", self.name, kind)

    async def _watchdog(self, ws: ClientConnection) -> None:
        while True:
            await asyncio.sleep(1.0)
            silence = self.silence()
            if silence is not None and silence > self.silence_s:
                self.on_state("stale", f"no message for {silence:.0f}s")
                with contextlib.suppress(Exception):
                    await ws.close(code=4001, reason="silence watchdog")
                return
