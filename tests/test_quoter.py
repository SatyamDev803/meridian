from decimal import Decimal

from meridian.config import StrategyParams
from meridian.core.quoter import Contract, Mode, ceil_tick, compute_quotes, floor_tick

D = Decimal
C = Contract(product_id=1, symbol="BTCUSD", tick_size=D("0.5"), contract_value=D("0.001"))


def params(**kw):
    return StrategyParams(
        **({"spread_bps": D("10"), "skew_bps": D("10"), "order_size": 10, "max_position": 50} | kw)
    )


def test_tick_rounding():
    assert floor_tick(D("100.74"), D("0.5")) == D("100.5")
    assert ceil_tick(D("100.01"), D("0.5")) == D("100.5")
    assert ceil_tick(D("100.5"), D("0.5")) == D("100.5")


def test_flat_inventory_is_symmetric_around_fair():
    q = compute_quotes(D("70000"), 0, params(), C)
    assert q.bid.price == D("69965.0")  # 70000 * (1 - 5bps) = 69965
    assert q.ask.price == D("70035.0")
    assert q.bid.size == q.ask.size == 10
    assert q.reservation == D("70000")


def test_long_inventory_shifts_quotes_down():
    flat = compute_quotes(D("70000"), 0, params(), C)
    long = compute_quotes(D("70000"), 25, params(), C)
    assert long.reservation < flat.reservation
    assert long.bid.price < flat.bid.price and long.ask.price < flat.ask.price


def test_short_inventory_shifts_quotes_up():
    flat = compute_quotes(D("70000"), 0, params(), C)
    short = compute_quotes(D("70000"), -25, params(), C)
    assert short.bid.price > flat.bid.price and short.ask.price > flat.ask.price


def test_at_max_long_only_the_ask_remains():
    q = compute_quotes(D("70000"), 50, params(), C)
    assert q.bid is None and q.ask is not None


def test_bid_size_capped_by_room_to_limit():
    q = compute_quotes(D("70000"), 45, params(), C)
    assert q.bid.size == 5 and q.ask.size == 10


def test_reduce_only_mode_quotes_reducing_side_sized_to_position():
    q = compute_quotes(D("70000"), 4, params(), C, mode=Mode.REDUCE_ONLY)
    assert q.bid is None and q.ask.size == 4
    flat = compute_quotes(D("70000"), 0, params(), C, mode=Mode.REDUCE_ONLY)
    assert flat.bid is None and flat.ask is None


def test_pull_and_halt_quote_nothing():
    for mode in (Mode.PULL, Mode.HALT):
        q = compute_quotes(D("70000"), 0, params(), C, mode=mode)
        assert q.bid is None and q.ask is None


def test_post_only_clamp_stays_behind_the_touch():
    q = compute_quotes(D("70000"), 0, params(), C, best_bid=D("69990"), best_ask=D("69960"))
    assert q.bid.price == D("69959.5")
    assert q.ask.price == D("70035.0")


def test_extra_spread_widens_both_sides():
    base = compute_quotes(D("70000"), 0, params(), C)
    wide = compute_quotes(D("70000"), 0, params(), C, extra_spread_bps=D("5"))
    assert wide.bid.price < base.bid.price and wide.ask.price > base.ask.price


def test_price_band_clamps():
    q = compute_quotes(D("70000"), 0, params(), C, band=(D("69980"), D("70010")))
    assert q.bid.price == D("69980") and q.ask.price == D("70010")


def test_no_fair_no_quotes():
    q = compute_quotes(None, 0, params(), C)
    assert q.bid is None and q.ask is None and q.note == "no fair value"
