from decimal import Decimal

import pytest

from meridian.core.ledger import Ledger

D = Decimal
CV = D("0.001")


def test_buy_then_sell_realizes_spread():
    led = Ledger(CV)
    led.apply_fill("buy", 10, D("70000"))
    res = led.apply_fill("sell", 10, D("70010"))
    assert res.realized_delta == D("0.1")  # 10 bucks a BTC * 0.01 BTC
    assert led.position == 0 and led.avg_price == 0


def test_average_entry_is_weighted():
    led = Ledger(CV)
    led.apply_fill("buy", 10, D("70000"))
    led.apply_fill("buy", 30, D("70040"))
    assert led.position == 40
    assert led.avg_price == D("70030")


def test_short_then_cover_profits_when_price_falls():
    led = Ledger(CV)
    led.apply_fill("sell", 20, D("70000"))
    res = led.apply_fill("buy", 20, D("69900"))
    assert res.realized_delta == D("2")
    assert led.position == 0


def test_flip_through_zero_opens_new_side_at_fill_price():
    led = Ledger(CV)
    led.apply_fill("buy", 10, D("70000"))
    res = led.apply_fill("sell", 25, D("70100"))
    assert res.realized_delta == D("1")  # only the 10 closed contracts realize
    assert led.position == -15
    assert led.avg_price == D("70100")


def test_fees_reduce_realized_and_rebates_add():
    led = Ledger(CV)
    led.apply_fill("buy", 10, D("70000"), fee=D("0.14"))
    assert led.realized == D("-0.14")
    led.apply_fill("sell", 10, D("70000"), fee=D("-0.05"))
    assert led.realized == D("-0.09")
    assert led.fees == D("0.09")


def test_unrealized_against_mark():
    led = Ledger(CV)
    led.apply_fill("sell", 10, D("70000"))
    assert led.unrealized(D("70100")) == D("-1")
    assert led.total(D("69900")) == D("1")


def test_adopt_replaces_position():
    led = Ledger(CV)
    led.apply_fill("buy", 10, D("70000"))
    led.adopt(-3, D("71000"))
    assert led.position == -3 and led.avg_price == D("71000")
    led.adopt(0, D("71000"))
    assert led.avg_price == 0


def test_rejects_bad_fills():
    led = Ledger(CV)
    with pytest.raises(ValueError):
        led.apply_fill("buy", 0, D("1"))
    with pytest.raises(ValueError):
        led.apply_fill("hold", 1, D("1"))
