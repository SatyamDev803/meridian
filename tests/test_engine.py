"""End-to-end engine behaviour against a fake exchange: no network, real strategy code."""

from decimal import Decimal

import pytest

from meridian.config import Settings
from meridian.core.engine import Engine
from meridian.core.quoter import Contract
from meridian.core.ratelimit import RateBudget

D = Decimal
C = Contract(product_id=84, symbol="BTCUSD", tick_size=D("0.1"), contract_value=D("0.001"))


class FakeRest:
    def __init__(self):
        self.budget = RateBudget()
        self.calls: list[tuple] = []
        self.position = {"size": 0, "entry_price": "0"}
        self.next_id = 1000
        self.fills: list = []

    async def aclose(self):
        pass

    async def place_limit(self, pid, side, size, price, coid, *, post_only=True):
        self.next_id += 1
        self.calls.append(("place", side, price, size))
        return {
            "id": self.next_id,
            "side": side,
            "client_order_id": coid,
            "limit_price": str(price),
            "size": size,
            "unfilled_size": size,
            "state": "open",
        }

    async def edit_order(self, pid, oid, price, size):
        self.calls.append(("edit", oid, price))
        return {
            "id": oid,
            "limit_price": str(price),
            "size": size,
            "unfilled_size": size,
            "state": "open",
        }

    async def cancel_order(self, pid, oid):
        self.calls.append(("cancel", oid))
        return {"id": oid, "state": "cancelled"}

    async def cancel_all(self, pid):
        self.calls.append(("cancel_all",))

    async def place_reduce_market(self, pid, side, size, coid):
        self.calls.append(("market", side, size))
        return {"id": 1}

    async def get_position(self, pid):
        return self.position

    async def get_wallet_balance(self, asset="USD"):
        return D("100")

    async def get_fills(self, pid, page_size=50):
        return self.fills

    async def set_leverage(self, pid, lev):
        return {}

    async def heartbeat_create(self, hid, sym, ttl_ms=30_000):
        self.calls.append(("hb_create", hid))
        return {}

    async def heartbeat_ack(self, hid, ttl):
        self.calls.append(("hb_ack", ttl))
        return {}


def make_engine() -> tuple[Engine, FakeRest]:
    s = Settings(
        _env_file=None, delta_api_key="k", delta_api_secret="s", database_url="sqlite:///:memory:"
    )
    rest = FakeRest()
    e = Engine(s, None, rest=rest)  # type: ignore[arg-type]
    e.contract = C
    e.ledger.contract_value = C.contract_value
    e.oms = e._make_oms(C)
    return e, rest


async def healthy_market(e: Engine, now: float, mark: str = "80000", ref: str = "80000") -> None:
    """Feed the minimum a healthy market needs: sockets up, mark, book, Binance."""
    e.public.connected = True
    e.public.last_message_at = now
    assert e.private is not None
    e.private.connected = e.private.authenticated = True
    e.private.last_message_at = now
    e.fair.on_ref(D(ref), D(ref), now)
    e.fair.on_mark(D(mark), now)
    e.fair.ref_at = now
    await e._on_public(
        {
            "type": "ob_updates",
            "sy": "BTCUSD",
            "action": "snapshot",
            "seq": 1,
            "a": [["80004.0", "100"]],
            "b": [["79996.0", "100"]],
        }
    )


async def test_start_cancels_arms_deadman_and_quotes_both_sides():
    e, rest = make_engine()
    ok, _ = await e.start_trading()
    assert ok and e.status == "running"
    assert rest.calls[0] == ("cancel_all",)
    assert any(c[0] == "hb_create" for c in rest.calls)
    await healthy_market(e, now=100.0)
    await e._tick(100.0, 0.25)
    places = [c for c in rest.calls if c[0] == "place"]
    assert {c[1] for c in places} == {"buy", "sell"}
    bid = next(c[2] for c in places if c[1] == "buy")
    ask = next(c[2] for c in places if c[1] == "sell")
    assert bid < D("80000") < ask


async def test_fill_moves_inventory_and_skews_quotes_down():
    e, _rest = make_engine()
    await e.start_trading()
    await healthy_market(e, now=100.0)
    await e._tick(100.0, 0.25)
    flat_bid = e.quotes.bid.price
    await e._on_private(
        {
            "type": "v2/user_trades",
            "sy": "BTCUSD",
            "f": "fill-1",
            "S": "buy",
            "s": 30,
            "p": "79970",
            "r": "maker",
            "o": 1,
            "c": "x",
            "po": 30,
        }
    )
    assert e.ledger.position == 30
    await e._on_private(
        {
            "type": "v2/user_trades",
            "sy": "BTCUSD",
            "f": "fill-1",
            "S": "buy",
            "s": 30,
            "p": "79970",
            "r": "maker",
            "o": 1,
            "c": "x",
            "po": 30,
        }
    )
    assert e.ledger.position == 30  # duplicate fill ignored
    await e._tick(100.25, 0.25)
    assert e.quotes.bid.price < flat_bid
    assert e.quotes.reservation < D("80000")


async def test_stale_reference_pulls_quotes():
    e, rest = make_engine()
    await e.start_trading()
    await healthy_market(e, now=100.0)
    await e._tick(100.0, 0.25)
    assert e.oms.live["buy"] is not None
    e.public.last_message_at = 110.0
    e.private.last_message_at = 110.0
    e.fair.on_mark(D("80000"), 110.0)  # mark fresh, Binance now 10s old
    await e._tick(110.0, 0.25)
    assert e.decision.mode.value == "pull"
    assert e.oms.live == {"buy": None, "sell": None}
    assert sum(1 for c in rest.calls if c[0] == "cancel") == 2


async def test_loss_limit_halts_and_flattens():
    e, rest = make_engine()
    await e.start_trading()
    await healthy_market(e, now=100.0)
    e.ledger.apply_fill("buy", 40, D("80000"))
    rest.position = {"size": 40, "entry_price": "80000"}
    e.update_params({"max_session_loss": D("5")})
    e.fair.on_mark(D("79800"), 100.0)  # 40 contracts * 0.001 * -200 = -8 USD
    e.fair.ref_at = 100.0
    await e._tick(100.0, 0.25)
    assert e.status == "halted"
    assert ("market", "sell", 40) in rest.calls
    assert ("hb_ack", 0) in rest.calls  # dead man's switch disarmed after a clean halt


async def test_kill_and_resume():
    e, _rest = make_engine()
    await e.start_trading()
    await e.kill("test")
    assert e.status == "halted"
    ok, _ = await e.start_trading()
    assert not ok
    await e.resume()
    assert e.status == "idle"


@pytest.mark.parametrize("name", ["stale_ref", "price_shock", "ledger_drift"])
async def test_chaos_actions(name):
    e, _ = make_engine()
    assert await e.chaos(name)


async def test_ledger_drift_books_at_mark_not_zero():
    e, _ = make_engine()
    e.fair.on_mark(D("80000"), 1.0)
    await e.chaos("ledger_drift")
    assert e.ledger.position == e.params.order_size
    assert e.ledger.avg_price == D("80000")
    assert e.ledger.unrealized(D("80000")) == 0


async def test_actual_delta_fee_replaces_estimate_in_ledger():
    e, rest = make_engine()
    await e.start_trading()
    await healthy_market(e, now=100.0)
    await e._on_private(
        {
            "type": "v2/user_trades",
            "sy": "BTCUSD",
            "f": "abc",
            "S": "buy",
            "s": 2,
            "p": "80000",
            "r": "maker",
            "o": 1,
            "c": "x",
            "po": 2,
        }
    )
    est = e.ledger.fees
    assert est == D("0.0002") * D("80000") * 2 * D("0.001")
    rest.fills = [{"id": "abc", "commission": "0.034"}]
    delta = e.perf.confirm_fee("abc", D("0.034"))
    e.ledger.adjust_fee(delta)
    assert e.ledger.fees == D("0.034")
    assert e.ledger.realized == D("-0.034")
    perf = e.state()["performance"]
    assert perf["feesConfirmed"] == 1 and perf["fills"] == 1
