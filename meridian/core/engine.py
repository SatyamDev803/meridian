"""The engine: wires feeds, strategy, risk, orders, ledger and fail-safes together.

Market data streams from the moment the app starts, so the dashboard is live even when the
bot is not trading. Trading has three states:

    idle     connected and computing quotes, but nothing rests on the exchange
    running  quotes rest on Delta and follow fair value and inventory
    halted   kill switch or loss limit; everything cancelled, needs a human to resume
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections import deque
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from meridian.config import Settings, StrategyParams
from meridian.core.decisions import DecisionLog, snapshot_inputs
from meridian.core.fair_value import FairValue
from meridian.core.ledger import Ledger
from meridian.core.oms import OrderManager
from meridian.core.performance import FillRecord, Performance
from meridian.core.quoter import Contract, Mode, Quotes, compute_quotes
from meridian.core.ratelimit import RateBudget
from meridian.core.risk import RiskDecision, RiskInputs, evaluate
from meridian.delta.book import BookError, ChecksumMismatch, ObUpdatesBook
from meridian.delta.rest import BudgetExhausted, DeltaError, DeltaRest, RateLimited
from meridian.delta.ws import DeltaSocket
from meridian.feeds.binance import BinanceRefFeed
from meridian.storage.db import DecisionRow, EventRow, FillRow, PnlRow, Store

log = logging.getLogger("meridian.engine")

D0 = Decimal(0)
CHECKSUM_DEGRADE_AFTER = 3


def f(x: Decimal | None) -> float | None:
    return None if x is None else float(x)


class Engine:
    def __init__(
        self, settings: Settings, store: Store | None, rest: DeltaRest | None = None
    ) -> None:
        self.settings = settings
        self.params: StrategyParams = settings.initial_params()
        self.store = store
        self.budget = RateBudget()
        self.rest = rest or DeltaRest(
            settings.delta_rest_url, settings.delta_api_key, settings.delta_api_secret, self.budget
        )
        if rest is not None:
            self.budget = rest.budget

        self.symbol = settings.symbol
        self.contract: Contract | None = None
        self.fair = FairValue()
        self.book = ObUpdatesBook(self.symbol)
        self.verify_checksum = True
        self.ledger = Ledger(Decimal("0.001"))
        self.oms: OrderManager | None = None

        self.status = "starting"
        self.halt_reason = ""
        self.system_status = "live"
        self.trading_status = "operational"
        self.band: tuple[Decimal, Decimal] | None = None
        self.exchange_position: int | None = None
        self.exchange_entry: Decimal | None = None
        self.perf = Performance()
        self.decisions = DecisionLog()
        self._last_inputs: dict | None = None
        self.wallet_balance: Decimal | None = None
        self.wallet_at: float | None = None

        self.api_errors = 0
        self.api_cooldown_until = 0.0
        self.deadman_id: str | None = None
        self.deadman_last_ack: float | None = None
        self.reconcile_state: dict[str, Any] = {"at": None, "ok": None, "detail": "not run yet"}
        self.decision: RiskDecision | None = None
        self.quotes: Quotes = Quotes.none("starting")
        self.preview = False
        self.last_mode: Mode | None = None
        self.session_baseline = D0
        self.peak_session = D0
        self.max_drawdown = D0
        self.seen_fills: set[str] = set()
        self.ref_bias_bps = D0
        self.ref_bias_until = 0.0

        self.started_at = time.monotonic()
        self.running_s = 0.0
        self.quoting_s = 0.0
        self.ticks = 0
        self.requotes = 0

        self.events: deque[dict] = deque(maxlen=300)
        self.price_history: deque[dict] = deque(maxlen=900)
        self.pnl_history: deque[dict] = deque(maxlen=900)
        self._event_seq = 0
        self._subscribers: set[asyncio.Queue] = set()
        self._tasks: list[asyncio.Task] = []
        self._trade_lock = asyncio.Lock()
        self._writes: set[asyncio.Task] = set()

        s = settings
        self.public = DeltaSocket(
            "delta-public",
            s.delta_ws_public_url,
            [
                {"name": "mark_price", "symbols": [f"MARK:{self.symbol}"]},
                {"name": "ob_updates", "symbols": [self.symbol]},
                {"name": "ticker", "symbols": [self.symbol]},
                {"name": "system_status"},
                {"name": "product_updates"},
            ],
            self._on_public,
            silence_s=s.ws_silence_s,
            on_state=self._socket_state("Delta market feed"),
        )
        self.private: DeltaSocket | None = None
        if s.has_keys:
            self.private = DeltaSocket(
                "delta-private",
                s.delta_ws_private_url,
                [
                    {"name": "orders", "symbols": [self.symbol]},
                    {"name": "positions", "symbols": [self.symbol]},
                    {"name": "v2/user_trades", "symbols": [self.symbol]},
                ],
                self._on_private,
                api_key=s.delta_api_key,
                api_secret=s.delta_api_secret,
                silence_s=s.ws_silence_s,
                on_state=self._socket_state("Delta account feed"),
            )
        self.binance = BinanceRefFeed(
            s.binance_ws_url,
            s.binance_symbol,
            self._on_ref,
            on_state=self._socket_state("Binance reference"),
        )

    # Lifecycle ---------------------------------------------------------------------------

    async def start(self) -> None:
        self.status = "idle"
        self.emit("system", "Meridian started. Streaming market data.")
        spawn = asyncio.create_task
        self._tasks = [
            spawn(self._load_contract(), name="contract"),
            spawn(self.public.run(), name="public-ws"),
            spawn(self.binance.run(), name="binance"),
            spawn(self._tick_loop(), name="tick"),
            spawn(self._broadcast_loop(), name="broadcast"),
            spawn(self._history_loop(), name="history"),
            spawn(self._reconcile_loop(), name="reconcile"),
            spawn(self._deadman_loop(), name="deadman"),
            spawn(self._fees_loop(), name="fees"),
        ]
        if self.private is not None:
            self._tasks.append(spawn(self.private.run(), name="private-ws"))
        else:
            self.emit("warning", "No API keys set. Market data only; trading is disabled.")
        if self.settings.auto_start and self.settings.has_keys:
            self._tasks.append(spawn(self._auto_start(), name="auto-start"))

    async def shutdown(self) -> None:
        if self.status == "running":
            await self.stop_trading("shutdown")
        for sock in (self.public, self.private):
            if sock is not None:
                sock.stop()
        self.binance.stop()
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
        await self.rest.aclose()

    async def _auto_start(self) -> None:
        for _ in range(60):
            if self.contract and self.private and self.private.ready and self.fair.mark:
                await self.start_trading()
                return
            await asyncio.sleep(1)

    def _make_oms(self, contract: Contract) -> OrderManager:
        oms = OrderManager(self.rest, contract, self.emit, self._on_api_result)
        oms.on_cancel_all = self._record_cancel_all
        return oms

    async def _load_contract(self) -> None:
        attempt = 0
        while self.contract is None:
            try:
                c = await self.rest.get_contract(self.symbol)
                self.contract = c
                self.ledger.contract_value = c.contract_value
                self.oms = self._make_oms(c)
                self.emit(
                    "system",
                    f"Loaded {c.symbol}: tick {c.tick_size}, contract {c.contract_value} BTC, "
                    f"maker fee {c.maker_fee * 100}%",
                )
            except Exception as exc:
                attempt += 1
                self.emit("warning", f"Could not load {self.symbol} contract yet: {exc}")
                await asyncio.sleep(min(30, 2**attempt))

    # Control -----------------------------------------------------------------------------

    def can_trade(self) -> tuple[bool, str]:
        if not self.settings.has_keys:
            return False, "Add Delta testnet API keys to start trading."
        if self.contract is None or self.oms is None:
            return False, "Still loading the contract from Delta."
        if self.status == "halted":
            return False, "Bot is halted. Resume first."
        return True, ""

    async def start_trading(self) -> tuple[bool, str]:
        async with self._trade_lock:
            ok, why = self.can_trade()
            if not ok:
                return False, why
            if self.status == "running":
                return True, "already running"
            assert self.contract and self.oms
            pid = self.contract.product_id
            with contextlib.suppress(Exception):
                await self.rest.set_leverage(pid, self.settings.leverage)
            await self.oms.cancel_all("clean start")
            await self._sync_position_from_exchange(adopt=True, reason="start")
            self.session_baseline = self.ledger.total(self.fair.mark)
            self.peak_session = D0
            self.max_drawdown = D0
            await self._refresh_wallet()
            p = self.params
            self.perf.reset(
                f"spread {p.spread_bps} bps, size {p.order_size}, skew {p.skew_bps} bps",
                p.model_dump(mode="json"),
                self.wallet_balance,
                self.ledger.unrealized(self.fair.mark),
            )
            await self._deadman_arm()
            self.status = "running"
            self.emit("control", "Trading started. Quoting both sides.")
            return True, "started"

    async def stop_trading(self, reason: str = "manual stop") -> tuple[bool, str]:
        async with self._trade_lock:
            if self.status == "running":
                self.status = "idle"
            if self.oms:
                await self.oms.cancel_all(reason)
            await self._deadman_disarm()
            self.emit("control", f"Trading stopped: {reason}.")
            return True, "stopped"

    async def kill(self, reason: str = "kill switch") -> tuple[bool, str]:
        async with self._trade_lock:
            self.status = "halted"
            self.halt_reason = reason
            if self.oms:
                await self.oms.cancel_all(reason)
            await self._deadman_disarm()
            self.emit("halt", f"Halted: {reason}.")
            return True, "halted"

    async def resume(self) -> tuple[bool, str]:
        if self.status != "halted":
            return False, "Not halted."
        self.status = "idle"
        self.halt_reason = ""
        self.session_baseline = self.ledger.total(self.fair.mark)
        self.peak_session = D0
        self.max_drawdown = D0
        self.emit("control", "Resumed. Session PnL reset. Press Start to quote again.")
        return True, "resumed"

    async def flatten(self, reason: str = "manual flatten") -> tuple[bool, str]:
        if self.contract is None or self.oms is None or not self.settings.has_keys:
            return False, "Not connected to an account."
        await self.oms.cancel_all(f"flatten: {reason}")
        await self._sync_position_from_exchange(adopt=True, reason="flatten")
        pos = self.ledger.position
        if pos == 0:
            return True, "already flat"
        side = "sell" if pos > 0 else "buy"
        try:
            await self.rest.place_reduce_market(
                self.contract.product_id, side, abs(pos), self.oms.next_client_id(side)
            )
            self.emit("control", f"Flattening {pos:+d} contracts with a reduce-only market order.")
            return True, "flatten sent"
        except Exception as exc:
            self.emit("error", f"Flatten failed: {exc}")
            return False, str(exc)

    def update_params(self, patch: dict[str, Any]) -> StrategyParams:
        merged = self.params.model_dump() | {k: v for k, v in patch.items() if v is not None}
        self.params = StrategyParams.model_validate(merged)
        changed = ", ".join(f"{k}={v}" for k, v in patch.items() if v is not None)
        self.emit("control", f"Parameters updated: {changed}.")
        return self.params

    # Chaos (demo fail-safes on purpose) ----------------------------------------------------

    async def chaos(self, name: str) -> str:
        now = time.monotonic()
        if name == "stale_ref":
            self.binance.paused_until = now + 10
            self.emit("chaos", "Chaos: Binance feed frozen for 10s.")
            return "Binance feed frozen for 10s"
        if name == "price_shock":
            self.ref_bias_bps = Decimal(60)
            self.ref_bias_until = now + 12
            self.emit("chaos", "Chaos: Binance reference shifted 60 bps for 12s.")
            return "reference shifted 60 bps for 12s"
        if name == "drop_feed":
            await self.public.force_reconnect("chaos: drop feed")
            self.emit("chaos", "Chaos: Delta market socket dropped.")
            return "Delta market socket dropped"
        if name == "ledger_drift":
            # A phantom fill at the mark price, so PnL stays sane until reconcile repairs it.
            price = self.fair.mark or self.ledger.avg_price
            pos = self.ledger.position
            size = self.params.order_size
            avg = (self.ledger.avg_price * abs(pos) + price * size) / (abs(pos) + size)
            self.ledger.adopt(pos + size, avg if pos >= 0 else price)
            self.emit(
                "chaos",
                f"Chaos: ledger told it bought {self.params.order_size} contracts that never "
                "traded. Reconcile should catch it.",
            )
            return "ledger drift injected"
        raise ValueError(f"unknown chaos action {name!r}")

    # Feed handlers -----------------------------------------------------------------------

    def _socket_state(self, label: str) -> Callable[[str, str], None]:
        def handler(state: str, detail: str) -> None:
            if state in {"connected", "authenticated"}:
                self.emit("feed", f"{label}: {state}.")
            elif state == "disconnected":
                self.emit("warning", f"{label}: disconnected, {detail}.")
                if label == "Delta market feed":
                    self.book.reset()
            elif state in {"auth_failed", "subscribe_error", "stale"}:
                self.emit("error", f"{label}: {state.replace('_', ' ')} ({detail}).")

        return handler

    def _on_ref(self, bid: Decimal, ask: Decimal) -> None:
        now = time.monotonic()
        if self.ref_bias_bps and now < self.ref_bias_until:
            k = 1 + self.ref_bias_bps / Decimal(10_000)
            bid, ask = bid * k, ask * k
        elif self.ref_bias_bps:
            self.ref_bias_bps = D0
        self.fair.on_ref(bid, ask, now)

    async def _on_public(self, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "mark_price":
            if msg.get("sy") == f"MARK:{self.symbol}":
                self.fair.on_mark(Decimal(str(msg["p"])), time.monotonic())
        elif kind == "ob_updates":
            if msg.get("sy", msg.get("symbol")) != self.symbol:
                return
            try:
                self.book.on_message(msg, verify_checksum=self.verify_checksum)
            except ChecksumMismatch as exc:
                if self.book.checksum_failures >= CHECKSUM_DEGRADE_AFTER:
                    self.verify_checksum = False
                    self.emit(
                        "warning",
                        "Order book checksum keeps disagreeing. Continuing on sequence "
                        "checks only.",
                    )
                else:
                    self.emit("warning", f"Order book {exc}. Resubscribing.")
                await self.public.resubscribe("ob_updates", [self.symbol])
            except BookError as exc:
                self.emit("warning", f"Order book {exc}. Resubscribing.")
                await self.public.resubscribe("ob_updates", [self.symbol])
        elif kind == "ticker":
            if msg.get("s", msg.get("sy")) == self.symbol or msg.get("sy") == self.symbol:
                for entry in msg.get("d", [msg]):
                    pb = entry.get("pb") or entry.get("price_band")
                    if isinstance(pb, list) and len(pb) == 2 and all(pb):
                        self.band = (Decimal(str(pb[0])), Decimal(str(pb[1])))
                    elif isinstance(pb, dict) and pb.get("lower_limit"):
                        self.band = (Decimal(pb["lower_limit"]), Decimal(pb["upper_limit"]))
        elif kind == "system_status":
            status = msg.get("status")
            if status and status != self.system_status:
                self.system_status = status
                self.emit("exchange", f"Exchange status: {status}.")
        elif kind == "product_updates":
            product = msg.get("product") or {}
            if product.get("symbol") == self.symbol and product.get("trading_status"):
                self.trading_status = product["trading_status"]
                self.emit("exchange", f"{self.symbol} trading status: {self.trading_status}.")

    async def _on_private(self, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "orders" and self.oms:
            self.oms.on_order_message(msg)
        elif kind == "positions":
            rows = msg.get("result") if msg.get("action") == "snapshot" else [msg]
            for p in rows or []:
                if p.get("product_symbol", p.get("symbol")) == self.symbol:
                    self.exchange_position = int(p.get("size") or 0)
                    ep = p.get("entry_price")
                    self.exchange_entry = Decimal(str(ep)) if ep else None
        elif kind == "v2/user_trades":
            if msg.get("sy") == self.symbol:
                await self._on_fill(msg)

    async def _on_fill(self, m: dict) -> None:
        fill_id = str(m.get("f"))
        if fill_id in self.seen_fills:
            return
        self.seen_fills.add(fill_id)
        side, size, price = m["S"], int(m["s"]), Decimal(str(m["p"]))
        role = m.get("r", "maker")
        cv = self.ledger.contract_value
        rate = (
            (self.contract.maker_fee if role == "maker" else self.contract.taker_fee)
            if self.contract
            else Decimal("0.0002")
        )
        fee = rate * price * size * cv
        res = self.ledger.apply_fill(side, size, price, fee, maker=role == "maker")
        fair_now = self.fair.estimate(
            use_drift=self.params.use_ref_drift, max_drift_bps=self.params.guard_bps
        ).fair
        self.perf.on_fill(
            FillRecord(fill_id, time.monotonic(), side, size, price, role, fair_now, fee)
        )
        if m.get("po") is not None:
            self.exchange_position = int(m["po"])
        self.emit(
            "fill",
            f"{'Bought' if side == 'buy' else 'Sold'} {size} @ {price} ({role}). "
            f"Position {res.position_after:+d}.",
            side=side,
            size=size,
            price=float(price),
            role=role,
            position=res.position_after,
            realized=float(res.realized_delta),
        )
        self._persist(
            FillRow(
                fill_id=fill_id,
                order_id=str(m.get("o")),
                client_order_id=m.get("c"),
                side=side,
                size=size,
                price=str(price),
                fee=str(fee),
                role=role,
                realized_delta=str(res.realized_delta),
                position_after=res.position_after,
            )
        )

    # API health --------------------------------------------------------------------------

    def _on_api_result(self, exc: Exception | None) -> None:
        if exc is None:
            self.api_errors = 0
            return
        if isinstance(exc, RateLimited | BudgetExhausted):
            return  # rate limiting has its own gate
        self.api_errors += 1
        if self.api_errors == self.settings.max_consecutive_api_errors:
            self.api_cooldown_until = time.monotonic() + self.settings.api_cooldown_s
            self.emit(
                "error",
                f"{self.api_errors} API errors in a row. Pausing quotes for "
                f"{self.settings.api_cooldown_s:.0f}s.",
            )

    # Main loop ---------------------------------------------------------------------------

    def session_pnl(self) -> Decimal:
        return self.ledger.total(self.fair.mark) - self.session_baseline

    def _risk_inputs(self, now: float, disagreement: Decimal | None) -> RiskInputs:
        s = self.settings
        priv = self.private
        cooling = now < self.api_cooldown_until
        if not cooling and self.api_errors >= s.max_consecutive_api_errors:
            self.api_errors = 0  # cooldown served, try again
        return RiskInputs(
            halted=self.status == "halted",
            halt_reason=self.halt_reason,
            has_keys=s.has_keys,
            public_ws_up=self.public.ready,
            public_silence_s=self.public.silence(now),
            private_ws_up=bool(priv and priv.ready),
            private_silence_s=priv.silence(now) if priv else None,
            mark_age_s=self.fair.mark_age(now),
            ref_age_s=self.fair.ref_age(now),
            book_synced=self.book.synced and not self.book.crossed(),
            disagreement_bps=disagreement,
            position=self.ledger.position,
            session_pnl=self.session_pnl(),
            rate_ok=self.budget.ok,
            rate_detail=self.budget.detail(),
            consecutive_api_errors=self.api_errors,
            api_cooling_down=cooling,
            system_status=self.system_status,
            trading_status=self.trading_status,
            ws_silence_s=s.ws_silence_s,
            mark_stale_s=s.mark_stale_s,
            ref_stale_s=s.ref_stale_s,
            max_api_errors=s.max_consecutive_api_errors,
        )

    async def _tick_loop(self) -> None:
        interval = self.settings.tick_interval_s
        last = time.monotonic()
        while True:
            await asyncio.sleep(interval)
            now = time.monotonic()
            dt, last = now - last, now
            try:
                await self._tick(now, dt)
            except Exception:
                log.exception("tick failed")
                self.emit("error", "Strategy tick failed. Pulling quotes as a precaution.")
                if self.oms and self.status == "running":
                    await self.oms.cancel_all("tick error")

    async def _tick(self, now: float, dt: float) -> None:
        self.ticks += 1
        ref_ok = (
            self.fair.ref_age(now) is not None
            and self.fair.ref_age(now) < self.settings.ref_stale_s
        )
        est = self.fair.estimate(
            use_drift=self.params.use_ref_drift,
            max_drift_bps=self.params.guard_bps,
            ref_usable=ref_ok,
        )
        decision = evaluate(self._risk_inputs(now, est.disagreement_bps), self.params)
        self.decision = decision

        if self.contract is None:
            self.quotes = Quotes.none("loading contract")
            return

        # While idle, preview what we would quote if only the account side were missing.
        mode = decision.mode
        account_only = {g.key for g in decision.failing} <= {"delta_private"}
        self.preview = self.status != "running" and mode is Mode.PULL and account_only
        if self.preview:
            mode = Mode.QUOTE
        self.quotes = compute_quotes(
            est.fair,
            self.ledger.position,
            self.params,
            self.contract,
            mode=mode,
            extra_spread_bps=decision.extra_spread_bps,
            best_bid=self.book.best_bid(),
            best_ask=self.book.best_ask(),
            band=self.band,
        )

        self._last_inputs = self._safe_snapshot(est, decision)

        running = self.status == "running" and self.oms is not None
        quoting = running and all(
            o is not None and o.order_id is not None
            for o in (self.oms.live.values() if self.oms else ())
        )
        self.perf.on_tick(now, est.fair, self.ledger.position, dt, running, quoting)

        if not running or self.oms is None:
            self.last_mode = None
            return

        self.running_s += dt
        if quoting:
            self.quoting_s += dt

        if decision.mode != self.last_mode:
            failing = ", ".join(g.label for g in decision.failing if g.action != "widen")
            if decision.mode is Mode.QUOTE:
                self.emit("risk", "All gates green. Quoting both sides.")
                if self.last_mode is not None:
                    self._record(lambda: self.decisions.resume(self._last_inputs))
            else:
                self.emit("risk", f"Mode {decision.mode.value.replace('_', ' ')}: {failing}.")
                gates = [g.as_dict() for g in decision.failing if g.action != "widen"]
                self._record(
                    lambda: self.decisions.pause(self._last_inputs, decision.mode.value, gates)
                )
            self.last_mode = decision.mode

        if decision.mode is Mode.HALT:
            await self.kill("session loss limit hit")
            if decision.flatten:
                await self.flatten("loss limit")
            return

        inputs = self._last_inputs
        actions = await self.oms.sync(self.quotes, self.params)
        self.requotes += sum(1 for a in actions if a.kind == "edit")
        if self.oms.last_results and inputs is not None:
            results = self.oms.last_results
            self._record(lambda: self.decisions.orders(inputs, results))

        session = self.session_pnl()
        self.peak_session = max(self.peak_session, session)
        self.max_drawdown = max(self.max_drawdown, self.peak_session - session)

    # Reconcile and dead man's switch -----------------------------------------------------

    async def _sync_position_from_exchange(self, *, adopt: bool, reason: str) -> int | None:
        if self.contract is None or not self.settings.has_keys:
            return None
        try:
            p = await self.rest.get_position(self.contract.product_id)
        except Exception as exc:
            self.reconcile_state = {"at": time.time(), "ok": None, "detail": f"failed: {exc}"}
            return None
        size = int((p or {}).get("size") or 0)
        entry = Decimal(str((p or {}).get("entry_price") or 0))
        self.exchange_position = size
        if adopt:
            self.ledger.adopt(size, entry)
            self.reconcile_state = {
                "at": time.time(),
                "ok": True,
                "detail": f"adopted exchange position {size:+d} on {reason}",
            }
        return size

    async def _reconcile_loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.reconcile_interval_s)
            if self.contract is None or not self.settings.has_keys:
                continue
            await self._refresh_wallet()
            ours = self.ledger.position
            theirs = await self._sync_position_from_exchange(adopt=False, reason="reconcile")
            if theirs is None:
                continue
            if theirs == ours:
                self.reconcile_state = {
                    "at": time.time(),
                    "ok": True,
                    "detail": f"ledger and exchange agree at {ours:+d}",
                }
                continue
            # A fill may be in flight on the socket. Look again before acting.
            await asyncio.sleep(1.5)
            theirs = await self._sync_position_from_exchange(adopt=False, reason="recheck")
            if theirs is None or theirs == self.ledger.position:
                continue
            before = self.ledger.position
            entry = self.exchange_entry or self.ledger.avg_price
            self.ledger.adopt(theirs, entry)
            self.reconcile_state = {
                "at": time.time(),
                "ok": False,
                "detail": f"break: ledger {before:+d}, exchange {theirs:+d}. Adopted exchange.",
            }
            self.emit(
                "reconcile",
                f"Reconcile break: ledger said {before:+d}, exchange says {theirs:+d}. "
                "Adopted the exchange position.",
            )

    # Decision log (read-only: nothing below may affect trading) ---------------------------

    def _safe_snapshot(self, est, decision) -> dict | None:
        try:
            return snapshot_inputs(
                est=est,
                decision=decision,
                quotes=self.quotes,
                params=self.params,
                position=self.ledger.position,
                best_bid=self.book.best_bid(),
                best_ask=self.book.best_ask(),
                band=self.band,
                preview=self.status != "running",
            )
        except Exception:
            log.exception("decision snapshot failed")
            return None

    def _record(self, make: Callable[[], dict]) -> None:
        try:
            rec = make()
        except Exception:
            log.exception("decision record failed")
            return
        self._publish("decision", rec)
        self._persist(
            DecisionRow(
                kind=rec["kind"], summary=rec["summary"], payload=json.dumps(rec, default=str)
            )
        )

    def _record_cancel_all(self, reason: str, ok: bool, leftovers: int) -> None:
        self._record(lambda: self.decisions.cancel_all(self._last_inputs, reason, ok, leftovers))

    async def _refresh_wallet(self) -> None:
        if not self.settings.has_keys:
            return
        try:
            self.wallet_balance = await self.rest.get_wallet_balance()
            self.wallet_at = time.time()
        except Exception as exc:
            log.warning("wallet refresh failed: %r", exc)

    async def _fees_loop(self) -> None:
        """Replace estimated fees with Delta's actual commission, which includes taxes."""
        while True:
            await asyncio.sleep(5)
            if self.contract is None or not self.perf.unconfirmed():
                continue
            try:
                fills = await self.rest.get_fills(self.contract.product_id)
            except Exception as exc:
                log.warning("fill sync failed: %r", exc)
                continue
            for f in fills or []:
                delta = self.perf.confirm_fee(str(f.get("id")), Decimal(str(f.get("commission"))))
                if delta is not None:
                    self.ledger.adjust_fee(delta)

    async def _deadman_arm(self) -> None:
        self.deadman_id = f"meridian-{int(time.time())}"
        try:
            await self.rest.heartbeat_create(
                self.deadman_id, self.symbol, self.settings.deadman_ttl_ms
            )
            await self.rest.heartbeat_ack(self.deadman_id, self.settings.deadman_ttl_ms)
            self.deadman_last_ack = time.monotonic()
            self.emit(
                "safety",
                f"Dead man's switch armed: Delta cancels our orders if we go silent for "
                f"{self.settings.deadman_ttl_ms // 1000}s.",
            )
        except Exception as exc:
            self.emit("warning", f"Could not arm dead man's switch: {exc}")

    async def _deadman_disarm(self) -> None:
        if self.deadman_id is None:
            return
        with contextlib.suppress(Exception):
            await self.rest.heartbeat_ack(self.deadman_id, 0)
        self.deadman_id = None
        self.deadman_last_ack = None

    async def _deadman_loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.deadman_interval_s)
            if self.status != "running" or self.deadman_id is None:
                continue
            try:
                await self.rest.heartbeat_ack(self.deadman_id, self.settings.deadman_ttl_ms)
                self.deadman_last_ack = time.monotonic()
            except (DeltaError, Exception) as exc:
                self.emit("warning", f"Dead man's switch heartbeat failed: {exc}")

    # Events, state and history -----------------------------------------------------------

    def emit(self, kind: str, message: str, **data: Any) -> None:
        self._event_seq += 1
        ev = {
            "id": self._event_seq,
            "ts": time.time() * 1000,
            "kind": kind,
            "message": message,
            "data": data,
        }
        self.events.appendleft(ev)
        log.info("[%s] %s", kind, message)
        self._publish("event", ev)
        if kind not in {"feed"}:
            self._persist(EventRow(kind=kind, message=message))

    def _persist(self, row: Any) -> None:
        if self.store is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        task = loop.create_task(asyncio.to_thread(self.store.add, row))
        self._writes.add(task)
        task.add_done_callback(self._writes.discard)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def _publish(self, kind: str, payload: Any) -> None:
        for q in list(self._subscribers):
            if q.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    q.get_nowait()
            q.put_nowait((kind, payload))

    async def _broadcast_loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.snapshot_interval_s)
            if self._subscribers:
                self._publish("state", self.state())

    async def _history_loop(self) -> None:
        n = 0
        while True:
            await asyncio.sleep(1.0)
            n += 1
            now_ms = time.time() * 1000
            q = self.quotes
            self.price_history.append(
                {
                    "t": now_ms,
                    "fair": f(
                        self.fair.estimate(
                            use_drift=self.params.use_ref_drift, max_drift_bps=self.params.guard_bps
                        ).fair
                    ),
                    "mark": f(self.fair.mark),
                    "ref": f(self.fair.ref_mid),
                    "bestBid": f(self.book.best_bid()),
                    "bestAsk": f(self.book.best_ask()),
                    "bid": f(q.bid.price) if q.bid else None,
                    "ask": f(q.ask.price) if q.ask else None,
                    "live": self.status == "running",
                }
            )
            if n % 2 == 0:
                point = {
                    "t": now_ms,
                    "realized": float(self.ledger.realized),
                    "unrealized": float(self.ledger.unrealized(self.fair.mark)),
                    "total": float(self.session_pnl()),
                    "position": self.ledger.position,
                }
                self.pnl_history.append(point)
                if n % 10 == 0 and (self.status == "running" or self.ledger.position):
                    self._persist(
                        PnlRow(
                            realized=str(self.ledger.realized),
                            unrealized=str(self.ledger.unrealized(self.fair.mark)),
                            total=str(self.session_pnl()),
                            position=self.ledger.position,
                            mark=str(self.fair.mark) if self.fair.mark else None,
                        )
                    )

    def history(self) -> dict:
        return {"prices": list(self.price_history), "pnl": list(self.pnl_history)}

    def _sock(self, sock: DeltaSocket | BinanceRefFeed | None, now: float) -> dict | None:
        if sock is None:
            return None
        last = sock.last_message_at
        return {
            "connected": sock.connected,
            "ready": getattr(sock, "ready", sock.connected),
            "silence_s": None if last is None else round(now - last, 2),
            "messages": sock.messages,
            "reconnects": sock.reconnects,
        }

    def state(self) -> dict:
        now = time.monotonic()
        est = self.fair.estimate(
            use_drift=self.params.use_ref_drift, max_drift_bps=self.params.guard_bps
        )
        q = self.quotes
        dec = self.decision
        mark = self.fair.mark
        led = self.ledger
        bb, ba = self.book.best_bid(), self.book.best_ask()
        mid = self.book.mid()
        can, why = self.can_trade()
        session = self.session_pnl()
        return {
            "ts": time.time() * 1000,
            "status": self.status,
            "haltReason": self.halt_reason,
            "canTrade": can,
            "cannotTradeReason": why,
            "hasKeys": self.settings.has_keys,
            "symbol": self.symbol,
            "chaosEnabled": self.settings.chaos_enabled,
            "contract": None
            if self.contract is None
            else {
                "productId": self.contract.product_id,
                "tickSize": float(self.contract.tick_size),
                "contractValue": float(self.contract.contract_value),
                "makerFee": float(self.contract.maker_fee),
            },
            "market": {
                "fair": f(est.fair),
                "mark": f(mark),
                "drift": f(est.drift),
                "ref": f(self.fair.ref_mid),
                "refBid": f(self.fair.ref_bid),
                "refAsk": f(self.fair.ref_ask),
                "basisBps": f(est.basis_bps),
                "disagreementBps": f(est.disagreement_bps),
                "bestBid": f(bb),
                "bestAsk": f(ba),
                "spreadBps": f((ba - bb) / mid * 10_000) if bb and ba and mid else None,
                "band": [float(self.band[0]), float(self.band[1])] if self.band else None,
                "book": self.book.depth(8),
                "bookSynced": self.book.synced,
                "checksumVerified": self.verify_checksum,
                "markAgeS": self.fair.mark_age(now),
                "refAgeS": self.fair.ref_age(now),
                "systemStatus": self.system_status,
                "tradingStatus": self.trading_status,
            },
            "quotes": {
                "bid": f(q.bid.price) if q.bid else None,
                "bidSize": q.bid.size if q.bid else 0,
                "ask": f(q.ask.price) if q.ask else None,
                "askSize": q.ask.size if q.ask else 0,
                "reservation": f(q.reservation),
                "halfSpreadBps": float(q.half_spread_bps),
                "inventoryRatio": float(q.inventory_ratio),
                "note": q.note,
                "preview": self.status != "running",
            },
            "orders": self.oms.snapshot() if self.oms else None,
            "position": {
                "contracts": led.position,
                "btc": float(led.position * led.contract_value),
                "avgPrice": f(led.avg_price) if led.position else None,
                "notionalUsd": float(abs(led.position) * led.contract_value * (mark or D0)),
                "exchangeContracts": self.exchange_position,
                "max": self.params.max_position,
            },
            "pnl": {
                "realized": float(led.realized),
                "unrealized": float(led.unrealized(mark)),
                "session": float(session),
                "fees": float(led.fees),
                "fills": led.fills,
                "makerRatio": (led.maker_fills / led.fills) if led.fills else None,
                "volumeUsd": float(led.notional),
                "maxDrawdown": float(self.max_drawdown),
            },
            "risk": {
                "mode": dec.mode.value if dec else "pull",
                "extraSpreadBps": float(dec.extra_spread_bps) if dec else 0.0,
                "gates": [g.as_dict() for g in dec.gates] if dec else [],
            },
            "params": self.params.model_dump(mode="json"),
            "health": {
                "public": self._sock(self.public, now),
                "private": self._sock(self.private, now),
                "binance": self._sock(self.binance, now),
                "rate": self.budget.snapshot(),
                "apiErrors": self.api_errors,
                "deadman": {
                    "armed": self.deadman_id is not None,
                    "lastAckS": None
                    if self.deadman_last_ack is None
                    else round(now - self.deadman_last_ack, 1),
                },
                "reconcile": self.reconcile_state,
            },
            "performance": self.perf.summary(
                session_pnl=session,
                unrealized=led.unrealized(mark),
                wallet_now=self.wallet_balance,
                max_drawdown=self.max_drawdown,
            ),
            "wallet": {
                "balance": f(self.wallet_balance),
                "checkedAt": None if self.wallet_at is None else self.wallet_at * 1000,
            },
            "metrics": {
                "uptimeS": round(now - self.started_at, 1),
                "runningS": round(self.running_s, 1),
                "livelinessPct": (self.quoting_s / self.running_s * 100)
                if self.running_s
                else None,
                "requotes": self.requotes,
                "ticks": self.ticks,
            },
        }
