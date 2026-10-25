from decimal import Decimal

from meridian.config import StrategyParams
from meridian.core.oms import LiveOrder, OrderManager, plan
from meridian.core.quoter import Contract, Quotes, QuoteSide
from meridian.delta.rest import DeltaError

D = Decimal
C = Contract(product_id=27, symbol="BTCUSD", tick_size=D("0.5"), contract_value=D("0.001"))
P = StrategyParams(requote_bps=D("2"))


def quotes(bid=None, ask=None, size=10):
    return Quotes(
        bid=QuoteSide(D(bid), size) if bid else None,
        ask=QuoteSide(D(ask), size) if ask else None,
        reservation=D("70000"),
        half_spread_bps=D("6"),
        inventory_ratio=D("0"),
    )


def live(side, price, size=10, unfilled=10, oid=1):
    return LiveOrder(side, f"c-{side}", D(price), size, unfilled, order_id=oid, state="open")


def kinds(actions):
    return sorted((a.kind, a.side) for a in actions)


def test_places_both_sides_when_nothing_is_live():
    acts = plan(quotes("69950", "70050"), {"buy": None, "sell": None}, set(), P)
    assert kinds(acts) == [("place", "buy"), ("place", "sell")]


def test_small_moves_do_not_requote():
    acts = plan(
        quotes("69951", "70050"),
        {"buy": live("buy", "69950"), "sell": live("sell", "70050")},
        set(),
        P,
    )
    assert acts == []


def test_large_move_edits():
    acts = plan(
        quotes("69900", "70050"),
        {"buy": live("buy", "69950"), "sell": live("sell", "70050")},
        set(),
        P,
    )
    assert kinds(acts) == [("edit", "buy")]


def test_missing_desired_side_cancels():
    acts = plan(
        quotes(None, "70050"),
        {"buy": live("buy", "69950"), "sell": live("sell", "70050")},
        set(),
        P,
    )
    assert kinds(acts) == [("cancel", "buy")]


def test_partial_fill_replaces():
    acts = plan(
        quotes("69950", "70050"), {"buy": live("buy", "69950", unfilled=4), "sell": None}, set(), P
    )
    assert kinds(acts) == [("cancel", "buy"), ("place", "sell")]


def test_in_flight_side_is_skipped_and_unacked_order_left_alone():
    unacked = LiveOrder("sell", "c", D("70050"), 10, 10, order_id=None)
    acts = plan(quotes("69950", "70100"), {"buy": None, "sell": unacked}, {"buy"}, P)
    assert acts == []


class FakeRest:
    def __init__(self):
        self.calls = []
        self.next_id = 100
        self.fail_place = None

    async def place_limit(self, pid, side, size, price, coid, *, post_only=True):
        self.calls.append(("place", side, price))
        if self.fail_place:
            raise self.fail_place
        self.next_id += 1
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
            "side": "buy",
            "limit_price": str(price),
            "size": size,
            "unfilled_size": size,
            "state": "open",
        }

    async def cancel_order(self, pid, oid):
        self.calls.append(("cancel", oid))
        return {"id": oid, "state": "cancelled"}

    async def cancel_all(self, pid):
        self.calls.append(("cancel_all", pid))
        return None


def make_oms(rest):
    events, api = [], []
    oms = OrderManager(rest, C, lambda kind, msg, **kw: events.append(kind), api.append)
    return oms, events, api


async def test_sync_places_then_tracks_ws_updates_and_fills():
    rest = FakeRest()
    oms, _, _ = make_oms(rest)
    await oms.sync(quotes("69950", "70050"), P)
    assert oms.live["buy"].order_id and oms.live["sell"].order_id
    buy = oms.live["buy"]
    oms.on_order_message(
        {
            "type": "orders",
            "action": "update",
            "order_id": buy.order_id,
            "client_order_id": buy.client_order_id,
            "side": "buy",
            "unfilled_size": 0,
            "state": "closed",
        }
    )
    assert oms.live["buy"] is None
    assert oms.live["sell"] is not None


async def test_rejection_clears_side_and_is_not_an_api_failure():
    rest = FakeRest()
    rest.fail_place = DeltaError(400, "post_only_order_cannot_be_matched")
    oms, events, api = make_oms(rest)
    await oms.sync(quotes("69950", None), P)
    assert oms.live["buy"] is None
    assert "reject" in events
    assert api == [None]


async def test_transport_error_reports_api_failure():
    rest = FakeRest()
    rest.fail_place = ConnectionError("boom")
    oms, _, api = make_oms(rest)
    await oms.sync(quotes("69950", None), P)
    assert isinstance(api[0], ConnectionError)
    assert oms.live["buy"] is None


async def test_cancel_all_clears_local_state():
    rest = FakeRest()
    oms, _, _ = make_oms(rest)
    await oms.sync(quotes("69950", "70050"), P)
    await oms.cancel_all("test")
    assert oms.live == {"buy": None, "sell": None}
    assert ("cancel_all", 27) in rest.calls


def test_client_ids_fit_delta_limit():
    oms, _, _ = make_oms(FakeRest())
    for _ in range(1000):
        cid = oms.next_client_id("sell")
    assert len(cid) <= 32 and oms.owns(cid)


async def test_cancel_all_sweeps_orders_the_exchange_kept():
    class StickyRest(FakeRest):
        async def get_open_orders(self, pid):
            return [{"id": 555, "side": "buy"}]

    rest = StickyRest()
    oms, events, _ = make_oms(rest)
    await oms.cancel_all("test")
    assert ("cancel", 555) in rest.calls
    assert "warning" in events
