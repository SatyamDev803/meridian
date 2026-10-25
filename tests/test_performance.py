from decimal import Decimal

from meridian.core.performance import FillRecord, Performance

D = Decimal


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def rec(fid, side, price, fair, at=0.0, fee="0.03", size=2):
    return FillRecord(fid, at, side, size, D(price), "maker", D(fair), D(fee))


def test_edge_and_markout_signs():
    clock = Clock()
    perf = Performance(clock)
    perf.reset("t", {}, D("100"))
    perf.on_fill(rec("a", "buy", "79990", "80000"))  # bought 10 below fair: +1.25 bps edge
    clock.t = 31
    perf.on_tick(31, D("79980"), 2, 0.25, True, True)  # fair fell 10 below our price
    s = perf.summary(session_pnl=D("-0.05"), unrealized=D(0), wallet_now=None, max_drawdown=D(0))
    assert round(s["edgeAtFillBps"], 2) == 1.25
    assert round(s["markoutBps"]["30"], 2) == -1.25
    assert round(s["adverseSelectionBps"], 2) == 2.5


def test_sell_edge_is_positive_above_fair():
    r = rec("b", "sell", "80010", "80000")
    assert r.bps_vs(D("80000")) > 0


def test_confirmed_fee_replaces_estimate_once():
    perf = Performance(Clock())
    perf.reset("t", {}, None)
    perf.on_fill(rec("a", "buy", "80000", "80000", fee="0.032"))
    assert perf.unconfirmed() == ["a"]
    assert perf.confirm_fee("a", D("0.034")) == D("0.002")
    assert perf.confirm_fee("a", D("0.034")) is None
    assert perf.confirm_fee("unknown", D("1")) is None
    s = perf.summary(session_pnl=D("-0.034"), unrealized=D(0), wallet_now=None, max_drawdown=D(0))
    assert s["fees"] == 0.034 and s["feesEstimated"] == 0.032 and s["feesConfirmed"] == 1
    assert round(s["grossPnl"], 6) == 0


def test_exchange_pnl_from_wallet_plus_unrealized():
    perf = Performance(Clock())
    perf.reset("t", {}, D("100"), unrealized_start=D("0.5"))
    s = perf.summary(
        session_pnl=D("-0.2"), unrealized=D("0.3"), wallet_now=D("100"), max_drawdown=D(0)
    )
    assert round(s["exchangePnl"], 6) == -0.2
    assert round(s["ledgerVsExchange"], 6) == 0


def test_duplicate_fills_ignored_and_inventory_tracked():
    perf = Performance(Clock())
    perf.reset("t", {}, None)
    perf.on_fill(rec("a", "buy", "1", "1"))
    perf.on_fill(rec("a", "buy", "1", "1"))
    perf.on_tick(1, D("1"), -7, 0.25, True, False)
    s = perf.summary(session_pnl=D(0), unrealized=D(0), wallet_now=None, max_drawdown=D(0))
    assert s["fills"] == 1 and s["maxInventory"] == 7 and s["quotingPct"] == 0
