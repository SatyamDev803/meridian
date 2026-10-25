"""Position and PnL from our own fills, in contracts and USD.

Signed weighted-average cost, ported from trade-pnl-service's ledger:
    adding to a position   -> average entry moves toward the fill price
    reducing a position    -> realized += (fill - entry) * closed * contract_value * sign
    crossing through zero  -> the remainder opens a new position at the fill price
Fees are subtracted from realized PnL; a negative fee (maker rebate) adds to it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class FillResult:
    realized_delta: Decimal
    position_after: int


class Ledger:
    def __init__(self, contract_value: Decimal) -> None:
        self.contract_value = contract_value
        self.position = 0
        self.avg_price = Decimal(0)
        self.realized = Decimal(0)
        self.fees = Decimal(0)
        self.volume_contracts = 0
        self.notional = Decimal(0)
        self.fills = 0
        self.maker_fills = 0

    def apply_fill(
        self, side: str, size: int, price: Decimal, fee: Decimal = Decimal(0), maker: bool = True
    ) -> FillResult:
        if size <= 0:
            raise ValueError("fill size must be positive")
        if side not in ("buy", "sell"):
            raise ValueError(f"bad side {side!r}")
        signed = size if side == "buy" else -size
        cv = self.contract_value
        realized = Decimal(0)

        if self.position == 0 or (self.position > 0) == (signed > 0):
            total = abs(self.position) + size
            self.avg_price = (self.avg_price * abs(self.position) + price * size) / total
            self.position += signed
        else:
            closed = min(size, abs(self.position))
            direction = 1 if self.position > 0 else -1
            realized = (price - self.avg_price) * closed * cv * direction
            self.position += signed
            if self.position == 0:
                self.avg_price = Decimal(0)
            elif (self.position > 0) != (direction > 0):
                self.avg_price = price  # flipped through zero

        realized -= fee
        self.realized += realized
        self.fees += fee
        self.volume_contracts += size
        self.notional += price * size * cv
        self.fills += 1
        self.maker_fills += 1 if maker else 0
        return FillResult(realized, self.position)

    def adjust_fee(self, delta: Decimal) -> None:
        """Replace an estimated fee with the actual one: delta = actual - estimate."""
        self.realized -= delta
        self.fees += delta

    def unrealized(self, mark: Decimal | None) -> Decimal:
        if mark is None or self.position == 0:
            return Decimal(0)
        return (mark - self.avg_price) * self.position * self.contract_value

    def total(self, mark: Decimal | None) -> Decimal:
        return self.realized + self.unrealized(mark)

    def adopt(self, position: int, avg_price: Decimal) -> None:
        """Take the exchange's view of the position (startup, or a reconcile break)."""
        self.position = position
        self.avg_price = avg_price if position != 0 else Decimal(0)
