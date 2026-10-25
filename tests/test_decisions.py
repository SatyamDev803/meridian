"""The decision log records the engine's real inputs and never changes what it trades."""

from decimal import Decimal

from meridian.config import StrategyParams
from meridian.core.oms import LiveOrder, plan
from meridian.core.quoter import Quotes, QuoteSide
from tests.test_engine import healthy_market, make_engine

D = Decimal
P = StrategyParams(requote_bps=D("2"))


def q(bid=None, ask=None, note=""):
    return Quotes(
        bid=QuoteSide(D(bid), 10) if bid else None,
        ask=QuoteSide(D(ask), 10) if ask else None,
        reservation=D("70000"),
        half_spread_bps=D("4"),
        inventory_ratio=D(0),
        note=note,
    )


def live(side, price, unfilled=10):
    return LiveOrder(side, f"c-{side}", D(price), 10, unfilled, order_id=7, state="open")


def test_plan_reasons_cover_every_rule():
    acts = plan(q("69950", "70050"), {"buy": None, "sell": None}, set(), P)
    assert [a.reason for a in acts] == ["no resting buy order", "no resting sell order"]

    acts = plan(
        q("69900", "70050"), {"buy": live("buy", "69950"), "sell": live("sell", "70050")}, set(), P
    )
    assert acts[0].kind == "edit" and acts[0].prev_price == D("69950")
    assert acts[0].reason.startswith("price moved 7.15 bps, threshold 2 bps")

    acts = plan(
        q(None, None, note="mode pull"), {"buy": live("buy", "69950"), "sell": None}, set(), P
    )
    assert acts[0].reason == "no buy quote wanted: mode pull"

    acts = plan(
        q(None, "70050"), {"buy": live("buy", "69950"), "sell": live("sell", "70050")}, set(), P
    )
    assert acts[0].reason == "no buy quote wanted: side at the inventory limit"

    acts = plan(q("69950", None), {"buy": live("buy", "69950", unfilled=4), "sell": None}, set(), P)
    assert acts[0].reason == "partially filled, 4 of 10 left; replacing"


async def test_order_decision_carries_the_exact_strategy_inputs():
    e, _ = make_engine()
    await e.start_trading()
    await healthy_market(e, now=100.0)
    await e._tick(100.0, 0.25)
    rec = next(r for r in e.decisions.list() if r["kind"] == "orders")
    i = rec["inputs"]
    assert {a["kind"] for a in rec["actions"]} == {"place"}
    assert all(a["outcome"].startswith("accepted, order") for a in rec["actions"])
    # Same objects the quoter used, not recomputed from the dashboard.
    assert i["final"]["bid"] == float(e.quotes.bid.price)
    assert i["final"]["ask"] == float(e.quotes.ask.price)
    assert i["pricing"]["reservation"] == float(e.quotes.reservation)
    assert i["pricing"]["spreadBps"] == float(e.params.spread_bps)
    assert i["pricing"]["volatilityAdjustmentBps"] == 0.0
    assert i["reference"]["deltaMark"] == 80000.0
    assert i["inventory"] == {"position": 0, "target": 0, "max": 50, "ratio": 0.0}
    assert len(i["risk"]["gates"]) == 12 and i["risk"]["mode"] == "quote"


async def test_skew_is_recorded_from_inventory():
    e, _ = make_engine()
    await e.start_trading()
    e.ledger.apply_fill("buy", 25, D("80000"))
    await healthy_market(e, now=100.0)
    await e._tick(100.0, 0.25)
    i = e.decisions.list()[0]["inputs"]
    assert i["inventory"]["ratio"] == 0.5
    assert i["pricing"]["skewAppliedBps"] == 5.0  # 0.5 * 10 bps
    assert i["pricing"]["reservation"] < 80000


async def test_safety_pause_and_resume_are_recorded_with_reasons():
    e, _ = make_engine()
    await e.start_trading()
    await healthy_market(e, now=100.0)
    await e._tick(100.0, 0.25)
    e.public.last_message_at = e.private.last_message_at = 110.0
    e.fair.on_mark(D("80000"), 110.0)  # Binance now 10s stale
    await e._tick(110.0, 0.25)
    pause = e.decisions.list(kind="pause")[0]
    assert pause["mode"] == "pull"
    assert any(r.startswith("Binance reference fresh") for r in pause["reasons"])
    cancels = e.decisions.list(kind="orders")[0]
    assert {a["kind"] for a in cancels["actions"]} == {"cancel"}
    assert all("mode pull" in a["reason"] for a in cancels["actions"])
    await healthy_market(e, now=111.0)
    await e._tick(111.0, 0.25)
    assert e.decisions.list(kind="resume")


async def test_cancel_all_is_recorded():
    e, _ = make_engine()
    await e.start_trading()
    await e.kill("test")
    kinds = [r["kind"] for r in e.decisions.list()]
    assert "cancel_all" in kinds
    rec = e.decisions.list(kind="cancel_all")[0]
    assert rec["reason"] == "test" and rec["ok"] is True


async def test_broken_decision_log_never_blocks_trading():
    e, rest = make_engine()

    def boom(*_a, **_k):
        raise RuntimeError("log down")

    e.decisions.orders = boom
    e.decisions.pause = boom
    await e.start_trading()
    await healthy_market(e, now=100.0)
    await e._tick(100.0, 0.25)
    assert {c[1] for c in rest.calls if c[0] == "place"} == {"buy", "sell"}
