from decimal import Decimal

from meridian.core.fair_value import FairValue

D = Decimal


def test_no_mark_means_no_fair():
    fv = FairValue()
    fv.on_ref(D("70000"), D("70001"), 0)
    assert fv.estimate(use_drift=True, max_drift_bps=D("25")).fair is None


def test_drift_adds_binance_move_since_last_mark():
    fv = FairValue()
    fv.on_ref(D("69999"), D("70001"), 0)
    fv.on_mark(D("70010"), 0)
    fv.on_ref(D("70019"), D("70021"), 1)  # Binance up 20 since the mark tick
    est = fv.estimate(use_drift=True, max_drift_bps=D("25"))
    assert est.drift == D("20") and est.fair == D("70030")
    assert fv.estimate(use_drift=False, max_drift_bps=D("25")).fair == D("70010")


def test_drift_is_capped():
    fv = FairValue()
    fv.on_ref(D("70000"), D("70000"), 0)
    fv.on_mark(D("70000"), 0)
    fv.on_ref(D("71000"), D("71000"), 1)
    est = fv.estimate(use_drift=True, max_drift_bps=D("10"))
    assert est.drift == D("70")  # 10 bps of 70000


def test_persistent_basis_is_learned_not_flagged():
    fv = FairValue()
    for i in range(50):
        fv.on_ref(D("70070"), D("70070"), i)  # Binance steadily 10 bps above
        fv.on_mark(D("70000"), i)
    est = fv.estimate(use_drift=False, max_drift_bps=D("25"))
    assert abs(est.disagreement_bps) < D("0.5")
    assert abs(est.basis_bps - D("10")) < D("0.5")


def test_sudden_jump_shows_as_disagreement():
    fv = FairValue()
    for i in range(10):
        fv.on_ref(D("70000"), D("70000"), i)
        fv.on_mark(D("70000"), i)
    fv.on_ref(D("70300"), D("70300"), 11)
    est = fv.estimate(use_drift=False, max_drift_bps=D("25"))
    assert est.disagreement_bps > D("40")


def test_basis_does_not_learn_from_a_shock():
    fv = FairValue()
    for i in range(10):
        fv.on_ref(D("70000"), D("70000"), i)
        fv.on_mark(D("70000"), i)
    for i in range(10, 20):
        fv.on_ref(D("70420"), D("70420"), i)  # 60 bps shock
        fv.on_mark(D("70000"), i)
    assert abs(fv.basis_bps) < D("0.01")
