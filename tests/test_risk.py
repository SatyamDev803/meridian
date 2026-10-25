from dataclasses import replace
from decimal import Decimal

import pytest

from meridian.config import StrategyParams
from meridian.core.quoter import Mode
from meridian.core.risk import RiskInputs, evaluate

D = Decimal
P = StrategyParams(max_position=50, max_session_loss=D("50"), guard_bps=D("25"), warn_bps=D("10"))

HEALTHY = RiskInputs(
    halted=False,
    halt_reason="",
    has_keys=True,
    public_ws_up=True,
    public_silence_s=0.2,
    private_ws_up=True,
    private_silence_s=1.0,
    mark_age_s=1.0,
    ref_age_s=0.1,
    book_synced=True,
    disagreement_bps=D("2"),
    position=0,
    session_pnl=D("0"),
    rate_ok=True,
    rate_detail="fine",
    consecutive_api_errors=0,
    api_cooling_down=False,
    system_status="live",
    trading_status="operational",
    ws_silence_s=35,
    mark_stale_s=6,
    ref_stale_s=3,
    max_api_errors=5,
)


def test_healthy_quotes_both_sides_and_all_gates_pass():
    d = evaluate(HEALTHY, P)
    assert d.mode is Mode.QUOTE
    assert all(g.ok for g in d.gates)
    assert len(d.gates) == 12


@pytest.mark.parametrize(
    "change, gate, mode",
    [
        ({"public_ws_up": False}, "delta_public", Mode.PULL),
        ({"public_silence_s": 40.0}, "delta_public", Mode.PULL),
        ({"private_ws_up": False}, "delta_private", Mode.PULL),
        ({"has_keys": False, "private_ws_up": False}, "delta_private", Mode.PULL),
        ({"mark_age_s": 7.0}, "mark_fresh", Mode.PULL),
        ({"mark_age_s": None}, "mark_fresh", Mode.PULL),
        ({"book_synced": False}, "book_synced", Mode.PULL),
        ({"ref_age_s": 4.0}, "ref_fresh", Mode.PULL),
        ({"disagreement_bps": D("30")}, "ref_agrees", Mode.PULL),
        ({"disagreement_bps": D("-30")}, "ref_agrees", Mode.PULL),
        ({"position": 50}, "inventory_ok", Mode.REDUCE_ONLY),
        ({"position": -50}, "inventory_ok", Mode.REDUCE_ONLY),
        ({"session_pnl": D("-50")}, "loss_ok", Mode.HALT),
        ({"rate_ok": False}, "rate_ok", Mode.PULL),
        ({"consecutive_api_errors": 5}, "api_healthy", Mode.PULL),
        ({"api_cooling_down": True}, "api_healthy", Mode.PULL),
        ({"system_status": "maintenance"}, "exchange_live", Mode.PULL),
        ({"trading_status": "disrupted_cancel_only"}, "exchange_live", Mode.PULL),
        ({"halted": True, "halt_reason": "kill"}, "not_halted", Mode.HALT),
    ],
)
def test_each_gate_fails_with_its_action(change, gate, mode):
    d = evaluate(replace(HEALTHY, **change), P)
    failing = {g.key for g in d.failing}
    assert gate in failing
    assert d.mode is mode


def test_warn_band_widens_but_keeps_quoting():
    d = evaluate(replace(HEALTHY, disagreement_bps=D("16")), P)
    assert d.mode is Mode.QUOTE
    assert d.extra_spread_bps == D("6")
    assert next(g for g in d.gates if g.key == "ref_agrees").ok


def test_worst_action_wins():
    d = evaluate(replace(HEALTHY, position=50, mark_age_s=None), P)
    assert d.mode is Mode.PULL


def test_loss_breach_with_position_requests_flatten():
    d = evaluate(replace(HEALTHY, session_pnl=D("-60"), position=7), P)
    assert d.mode is Mode.HALT and d.flatten
    d2 = evaluate(replace(HEALTHY, session_pnl=D("-60"), position=0), P)
    assert not d2.flatten
