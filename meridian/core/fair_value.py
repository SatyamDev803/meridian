"""Fair value: Delta's mark price, cross-checked (and optionally nudged) by Binance.

* Delta publishes `mark_price` every ~2 s. That is our anchor: it is the price Delta itself
  marks positions at, so it is the hardest number to argue with.
* Binance's best bid/offer arrives ~10x a second. Between two mark ticks we add Binance's
  move since the last mark tick ("drift"), so our quotes do not sit stale for two seconds.
* Delta perp and Binance spot normally trade a few bps apart (funding, USD vs USDT). We learn
  that normal gap as a slow EWMA ("basis") and only treat the *deviation* from it as
  disagreement. A big deviation means one of the two feeds is wrong, so we stop quoting.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

BPS = Decimal(10_000)
BASIS_ALPHA = Decimal("0.05")  # per mark tick (~2 s), so the basis adapts over about a minute
BASIS_FREEZE_BPS = Decimal(15)  # a jump this large is news, not basis: do not learn from it


@dataclass(frozen=True)
class FairEstimate:
    fair: Decimal | None
    mark: Decimal | None
    ref_mid: Decimal | None
    drift: Decimal
    basis_bps: Decimal | None
    disagreement_bps: Decimal | None


class FairValue:
    def __init__(self) -> None:
        self.mark: Decimal | None = None
        self.mark_at: float | None = None
        self.ref_mid: Decimal | None = None
        self.ref_bid: Decimal | None = None
        self.ref_ask: Decimal | None = None
        self.ref_at: float | None = None
        self.ref_at_mark: Decimal | None = None
        self.basis_bps: Decimal | None = None

    def on_mark(self, price: Decimal, now: float) -> None:
        self.mark = price
        self.mark_at = now
        self.ref_at_mark = self.ref_mid
        if self.ref_mid is not None and price > 0:
            observed = (self.ref_mid - price) / price * BPS
            if self.basis_bps is None:
                self.basis_bps = observed
            elif abs(observed - self.basis_bps) <= BASIS_FREEZE_BPS:
                self.basis_bps += BASIS_ALPHA * (observed - self.basis_bps)

    def on_ref(self, bid: Decimal, ask: Decimal, now: float) -> None:
        self.ref_bid, self.ref_ask = bid, ask
        self.ref_mid = (bid + ask) / 2
        self.ref_at = now
        if self.ref_at_mark is None:
            self.ref_at_mark = self.ref_mid

    def mark_age(self, now: float) -> float | None:
        return None if self.mark_at is None else now - self.mark_at

    def ref_age(self, now: float) -> float | None:
        return None if self.ref_at is None else now - self.ref_at

    def estimate(
        self, *, use_drift: bool, max_drift_bps: Decimal, ref_usable: bool = True
    ) -> FairEstimate:
        if self.mark is None:
            return FairEstimate(None, None, self.ref_mid, Decimal(0), self.basis_bps, None)

        disagreement: Decimal | None = None
        drift = Decimal(0)
        if self.ref_mid is not None and self.mark > 0:
            live_basis = (self.ref_mid - self.mark) / self.mark * BPS
            basis = live_basis if self.basis_bps is None else self.basis_bps
            disagreement = live_basis - basis
            if use_drift and ref_usable and self.ref_at_mark is not None:
                drift = self.ref_mid - self.ref_at_mark
                cap = self.mark * max_drift_bps / BPS
                drift = max(-cap, min(cap, drift))

        return FairEstimate(
            fair=self.mark + drift,
            mark=self.mark,
            ref_mid=self.ref_mid,
            drift=drift,
            basis_bps=self.basis_bps,
            disagreement_bps=disagreement,
        )
