"""Order manager: makes the orders resting on Delta match the quotes we want.

`plan()` is a pure diff between desired quotes and live orders, so it is unit tested.
`execute()` sends the resulting actions concurrently, one in flight per side at most.
Live order state is updated from REST responses and from the private `orders` channel,
whichever arrives first.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from meridian.config import StrategyParams
from meridian.core.quoter import Contract, Quotes, QuoteSide

log = logging.getLogger("meridian.oms")

BPS = Decimal(10_000)
SIDES = ("buy", "sell")
TERMINAL = {"closed", "cancelled"}


class Rest(Protocol):
    async def place_limit(
        self, product_id, side, size, price, client_order_id, *, post_only=True
    ): ...
    async def edit_order(self, product_id, order_id, price, size): ...
    async def cancel_order(self, product_id, order_id): ...
    async def cancel_all(self, product_id): ...


@dataclass
class LiveOrder:
    side: str
    client_order_id: str
    price: Decimal
    size: int
    unfilled: int
    order_id: int | None = None
    state: str = "pending_new"
    updated_at: float = 0.0

    def as_dict(self) -> dict:
        return {
            "side": self.side,
            "client_order_id": self.client_order_id,
            "order_id": self.order_id,
            "price": format(self.price, "f"),
            "size": self.size,
            "unfilled": self.unfilled,
            "state": self.state,
        }


@dataclass(frozen=True)
class Action:
    kind: str  # place | edit | cancel
    side: str
    price: Decimal | None = None
    size: int | None = None
    reason: str = ""  # why plan() chose this action (recorded, never acted on)
    prev_price: Decimal | None = None


def plan(
    desired: Quotes,
    live: dict[str, LiveOrder | None],
    in_flight: set[str],
    params: StrategyParams,
) -> list[Action]:
    actions: list[Action] = []
    for side in SIDES:
        if side in in_flight:
            continue
        want: QuoteSide | None = desired.bid if side == "buy" else desired.ask
        have = live.get(side)
        if want is None:
            if have is not None:
                why = desired.note or "side at the inventory limit"
                actions.append(
                    Action(
                        "cancel",
                        side,
                        reason=f"no {side} quote wanted: {why}",
                        prev_price=have.price,
                    )
                )
            continue
        if have is None:
            actions.append(
                Action("place", side, want.price, want.size, reason=f"no resting {side} order")
            )
            continue
        if have.order_id is None:
            continue  # placed but not acknowledged yet
        if have.unfilled != want.size:
            # Partially filled or size changed: replace it cleanly.
            why = (
                f"partially filled, {have.unfilled} of {have.size} left"
                if have.unfilled < have.size
                else f"size changed from {have.unfilled} to {want.size}"
            )
            actions.append(
                Action("cancel", side, reason=f"{why}; replacing", prev_price=have.price)
            )
            continue
        moved_bps = abs(want.price - have.price) / have.price * BPS
        if moved_bps >= params.requote_bps:
            actions.append(
                Action(
                    "edit",
                    side,
                    want.price,
                    want.size,
                    reason=f"price moved {moved_bps:.2f} bps, threshold {params.requote_bps} bps",
                    prev_price=have.price,
                )
            )
    return actions


class OrderManager:
    def __init__(
        self,
        rest: Rest,
        contract: Contract,
        emit: Callable[..., None],
        on_api_result: Callable[[Exception | None], None],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.rest = rest
        self.contract = contract
        self.emit = emit
        self.on_api_result = on_api_result
        self.clock = clock
        self.live: dict[str, LiveOrder | None] = {"buy": None, "sell": None}
        self.in_flight: set[str] = set()
        self._ids = itertools.count(1)
        self._session = format(int(time.time()) % 1_000_000, "06d")
        self.stats = {"placed": 0, "edited": 0, "cancelled": 0, "rejected": 0}
        # Read-only hooks for the decision log; trading never depends on them.
        self.last_results: list[tuple[Action, str]] = []
        self._outcomes: dict[str, str] = {}  # per side: one action in flight per side
        self.on_cancel_all: Callable[[str, bool, int], None] | None = None

    def next_client_id(self, side: str) -> str:
        return f"mrd-{self._session}-{side[0]}-{next(self._ids)}"  # well under 32 chars

    def owns(self, client_order_id: str | None) -> bool:
        return bool(client_order_id) and client_order_id.startswith(f"mrd-{self._session}-")

    async def sync(self, desired: Quotes, params: StrategyParams) -> list[Action]:
        actions = plan(desired, self.live, self.in_flight, params)
        if actions:
            outcomes = await asyncio.gather(*(self._run(a) for a in actions))
            self.last_results = list(zip(actions, outcomes, strict=True))
        else:
            self.last_results = []
        return actions

    async def _guarded(self, side: str, coro: Awaitable) -> dict | None:
        from meridian.delta.rest import DeltaError

        self.in_flight.add(side)
        self._outcomes[side] = "accepted"
        try:
            result = await coro
            self.on_api_result(None)
            return result
        except DeltaError as exc:
            self._outcomes[side] = f"rejected by Delta: {exc.code}"
            self.on_api_result(None)  # the exchange answered; it is healthy
            self.stats["rejected"] += 1
            self.emit("reject", f"{side} order rejected: {exc.code}", side=side, code=exc.code)
            if exc.code in {"open_order_not_found", "order_not_found", "order_already_closed"}:
                self.live[side] = None
            return None
        except Exception as exc:
            self._outcomes[side] = f"failed: {type(exc).__name__}"
            self.on_api_result(exc)
            self.emit("error", f"{side} order call failed: {exc}", side=side)
            return None
        finally:
            self.in_flight.discard(side)

    async def _run(self, a: Action) -> str:
        pid = self.contract.product_id
        if a.kind == "place":
            assert a.price is not None and a.size is not None
            coid = self.next_client_id(a.side)
            self.live[a.side] = LiveOrder(
                a.side, coid, a.price, a.size, a.size, updated_at=self.clock()
            )
            res = await self._guarded(
                a.side, self.rest.place_limit(pid, a.side, a.size, a.price, coid)
            )
            if res is None:
                if self.live[a.side] and self.live[a.side].client_order_id == coid:
                    self.live[a.side] = None
                return self._outcomes.get(a.side, "unknown")
            self.stats["placed"] += 1
            self._absorb({"side": a.side} | res)
            return f"accepted, order {res.get('id')}"
        elif a.kind == "edit":
            order = self.live[a.side]
            if order is None or order.order_id is None:
                return "skipped: order already gone"
            assert a.price is not None and a.size is not None
            res = await self._guarded(
                a.side, self.rest.edit_order(pid, order.order_id, a.price, order.size)
            )
            if res is not None:
                self.stats["edited"] += 1
                self._absorb({"side": a.side} | res)
                return f"accepted, order {order.order_id}"
            return self._outcomes.get(a.side, "unknown")
        elif a.kind == "cancel":
            order = self.live[a.side]
            if order is None or order.order_id is None:
                self.live[a.side] = None
                return "skipped: order already gone"
            res = await self._guarded(a.side, self.rest.cancel_order(pid, order.order_id))
            if res is not None:
                self.stats["cancelled"] += 1
                if self.live[a.side] is order:
                    self.live[a.side] = None
                return f"accepted, order {order.order_id}"
            return self._outcomes.get(a.side, "unknown")
        return "skipped: unknown action"

    def _absorb(self, o: dict) -> None:
        """Apply an order object from REST or the `orders` channel."""
        side = o.get("side")
        coid = o.get("client_order_id")
        if side not in SIDES:
            return
        current = self.live.get(side)
        oid = o.get("id") or o.get("order_id")
        matches = current is not None and (
            (coid and current.client_order_id == coid)
            or (oid is not None and current.order_id == oid)
        )
        if not matches:
            return
        assert current is not None
        state = o.get("state", current.state)
        if state in TERMINAL or o.get("action") == "delete":
            self.live[side] = None
            return
        current.order_id = int(oid) if oid is not None else current.order_id
        if o.get("limit_price") is not None:
            current.price = Decimal(str(o["limit_price"]))
        if o.get("size") is not None:
            current.size = int(o["size"])
        if o.get("unfilled_size") is not None:
            current.unfilled = int(o["unfilled_size"])
        current.state = state
        current.updated_at = self.clock()

    def on_order_message(self, msg: dict) -> None:
        if msg.get("action") == "snapshot":
            for o in msg.get("result", []):
                self._absorb(o)
            return
        self._absorb(msg)

    async def cancel_all(self, reason: str) -> bool:
        from meridian.delta.rest import DeltaError

        try:
            await self.rest.cancel_all(self.contract.product_id)
            self.on_api_result(None)
            ok = True
        except DeltaError as exc:
            self.on_api_result(None)
            self.emit("error", f"cancel all rejected: {exc.code}")
            ok = False
        except Exception as exc:
            self.on_api_result(exc)
            self.emit("error", f"cancel all failed: {exc}")
            ok = False
        self.live = {"buy": None, "sell": None}
        leftovers = await self._sweep_leftovers()
        if leftovers:
            self.emit(
                "warning", f"Cancel all left {leftovers} orders open. Cancelled them one by one."
            )
        self.emit("cancel_all", f"Cancelled all orders: {reason}", reason=reason)
        if self.on_cancel_all is not None:
            try:
                self.on_cancel_all(reason, ok, leftovers)
            except Exception:
                log.exception("decision hook failed")
        return ok

    async def _sweep_leftovers(self) -> int:
        """Trust but verify: list open orders on the exchange and cancel any survivors."""
        lister = getattr(self.rest, "get_open_orders", None)
        if lister is None:
            return 0
        try:
            remaining = await lister(self.contract.product_id) or []
        except Exception as exc:
            self.emit("warning", f"Could not verify cancel all: {exc}")
            return 0
        for o in remaining:
            try:
                await self.rest.cancel_order(self.contract.product_id, int(o["id"]))
            except Exception as exc:
                self.emit("error", f"Could not cancel leftover order {o.get('id')}: {exc}")
        return len(remaining)

    def snapshot(self) -> dict:
        return {
            "live": {s: (o.as_dict() if o else None) for s, o in self.live.items()},
            "in_flight": sorted(self.in_flight),
            "stats": dict(self.stats),
        }
