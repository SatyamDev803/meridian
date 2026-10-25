"""Session performance: where the money came from and where it went.

For every fill we record
    edge at fill   how far inside fair value we traded (positive: bought below / sold above fair)
    markout        the same measure N seconds later, against where fair value went next
    fee            first estimated from the published rate, then replaced by Delta's actual
                   commission from GET /v2/fills (which includes taxes on top of the rate)

Edge minus markout is adverse selection: how much of the spread the market took back.
The session also tracks the exchange's own view, so the ledger can be checked against the
change in Delta's wallet balance (which includes fees, taxes and funding).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from decimal import Decimal

BPS = Decimal(10_000)
HORIZONS = (5, 30)  # seconds


@dataclass
class FillRecord:
    fill_id: str
    at: float  # monotonic
    side: str
    size: int
    price: Decimal
    role: str
    fair_at_fill: Decimal | None
    fee_estimate: Decimal
    fee_actual: Decimal | None = None
    markouts: dict[int, Decimal | None] = field(default_factory=lambda: dict.fromkeys(HORIZONS))

    @property
    def sign(self) -> int:
        return 1 if self.side == "buy" else -1

    def bps_vs(self, reference: Decimal | None) -> Decimal | None:
        if reference is None or self.price <= 0:
            return None
        return self.sign * (reference - self.price) / self.price * BPS

    @property
    def fee(self) -> Decimal:
        return self.fee_actual if self.fee_actual is not None else self.fee_estimate


class Performance:
    def __init__(self, clock=time.monotonic) -> None:
        self.clock = clock
        self.reset("startup", {}, None)

    def reset(
        self,
        label: str,
        params: dict,
        wallet_start: Decimal | None,
        unrealized_start: Decimal = Decimal(0),
    ) -> None:
        self.label = label
        self.params = params
        self.started_at = self.clock()
        self.started_wall = time.time()
        self.fills: list[FillRecord] = []
        self.by_id: dict[str, FillRecord] = {}
        self.wallet_start = wallet_start
        self.unrealized_start = unrealized_start
        self.max_inventory = 0
        self.quoting_s = 0.0
        self.running_s = 0.0

    # Recording ----------------------------------------------------------------------------

    def on_fill(self, rec: FillRecord) -> None:
        if rec.fill_id in self.by_id:
            return
        self.fills.append(rec)
        self.by_id[rec.fill_id] = rec

    def confirm_fee(self, fill_id: str, actual: Decimal) -> Decimal | None:
        """Record Delta's actual commission. Returns actual minus estimate, or None if unknown."""
        rec = self.by_id.get(fill_id)
        if rec is None or rec.fee_actual is not None:
            return None
        rec.fee_actual = actual
        return actual - rec.fee_estimate

    def unconfirmed(self) -> list[str]:
        return [r.fill_id for r in self.fills if r.fee_actual is None]

    def on_tick(
        self,
        now: float,
        fair: Decimal | None,
        position: int,
        dt: float,
        running: bool,
        quoting: bool,
    ) -> None:
        self.max_inventory = max(self.max_inventory, abs(position))
        if running:
            self.running_s += dt
            if quoting:
                self.quoting_s += dt
        if fair is None:
            return
        for rec in self.fills:
            for h in HORIZONS:
                if rec.markouts[h] is None and now - rec.at >= h:
                    rec.markouts[h] = rec.bps_vs(fair)

    # Reporting ----------------------------------------------------------------------------

    @staticmethod
    def _avg(values: list[tuple[Decimal, int]]) -> float | None:
        total = sum(w for _, w in values)
        if not total:
            return None
        return float(sum(v * w for v, w in values) / total)

    def summary(
        self,
        *,
        session_pnl: Decimal,
        unrealized: Decimal,
        wallet_now: Decimal | None,
        max_drawdown: Decimal,
    ) -> dict:
        fills = self.fills
        fees = sum((r.fee for r in fills), Decimal(0))
        fees_est = sum((r.fee_estimate for r in fills), Decimal(0))
        confirmed = sum(1 for r in fills if r.fee_actual is not None)
        edge = [(r.bps_vs(r.fair_at_fill), r.size) for r in fills]
        edge = [(v, w) for v, w in edge if v is not None]
        marks = {
            h: [(r.markouts[h], r.size) for r in fills if r.markouts[h] is not None]
            for h in HORIZONS
        }
        hours = max(self.clock() - self.started_at, 1.0) / 3600
        exchange_pnl = None
        if wallet_now is not None and self.wallet_start is not None:
            exchange_pnl = wallet_now - self.wallet_start + (unrealized - self.unrealized_start)
        edge_avg = self._avg(edge)
        m30 = self._avg(marks[30])
        return {
            "label": self.label,
            "params": self.params,
            "startedAt": self.started_wall * 1000,
            "durationS": round(self.clock() - self.started_at, 1),
            "fills": len(fills),
            "fillsPerHour": round(len(fills) / hours, 1),
            "makerShare": (sum(1 for r in fills if r.role == "maker") / len(fills))
            if fills
            else None,
            "contracts": sum(r.size for r in fills),
            "edgeAtFillBps": edge_avg,
            "markoutBps": {str(h): self._avg(marks[h]) for h in HORIZONS},
            "adverseSelectionBps": (edge_avg - m30)
            if edge_avg is not None and m30 is not None
            else None,
            "grossPnl": float(session_pnl + fees),
            "fees": float(fees),
            "feesEstimated": float(fees_est),
            "feesConfirmed": confirmed,
            "netPnl": float(session_pnl),
            "exchangePnl": float(exchange_pnl) if exchange_pnl is not None else None,
            "ledgerVsExchange": float(session_pnl - exchange_pnl)
            if exchange_pnl is not None
            else None,
            "maxInventory": self.max_inventory,
            "maxDrawdown": float(max_drawdown),
            "quotingPct": (self.quoting_s / self.running_s * 100) if self.running_s else None,
        }
