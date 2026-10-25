"""Turns fair value and inventory into the two prices we show the market.

    q   = clamp(position / max_position, -1, 1)          how full the inventory is
    r   = fair * (1 - q * skew_bps / 10_000)             reservation price, leans against inventory
    bid = floor_to_tick(r * (1 - half_spread))
    ask = ceil_to_tick (r * (1 + half_spread))

Long inventory pushes both prices down so our ask is the likelier one to trade, which sells
inventory back toward flat. Short inventory does the opposite. This is the core of the
Avellaneda-Stoikov idea without the stochastic-control maths.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from enum import StrEnum

from meridian.config import StrategyParams

BPS = Decimal(10_000)


class Mode(StrEnum):
    QUOTE = "quote"  # both sides
    REDUCE_ONLY = "reduce_only"  # only the side that shrinks inventory
    PULL = "pull"  # no quotes
    HALT = "halt"  # no quotes, needs a human


@dataclass(frozen=True)
class Contract:
    product_id: int
    symbol: str
    tick_size: Decimal
    contract_value: Decimal
    maker_fee: Decimal = Decimal("0.0002")
    taker_fee: Decimal = Decimal("0.0005")


@dataclass(frozen=True)
class QuoteSide:
    price: Decimal
    size: int


@dataclass(frozen=True)
class Quotes:
    bid: QuoteSide | None
    ask: QuoteSide | None
    reservation: Decimal | None
    half_spread_bps: Decimal
    inventory_ratio: Decimal
    note: str = ""

    @staticmethod
    def none(note: str, inventory_ratio: Decimal = Decimal(0)) -> Quotes:
        return Quotes(None, None, None, Decimal(0), inventory_ratio, note)


def floor_tick(price: Decimal, tick: Decimal) -> Decimal:
    return (price / tick).to_integral_value(rounding=ROUND_FLOOR) * tick


def ceil_tick(price: Decimal, tick: Decimal) -> Decimal:
    return (price / tick).to_integral_value(rounding=ROUND_CEILING) * tick


def compute_quotes(
    fair: Decimal | None,
    position: int,
    params: StrategyParams,
    contract: Contract,
    *,
    mode: Mode = Mode.QUOTE,
    extra_spread_bps: Decimal = Decimal(0),
    best_bid: Decimal | None = None,
    best_ask: Decimal | None = None,
    band: tuple[Decimal, Decimal] | None = None,
) -> Quotes:
    q = max(Decimal(-1), min(Decimal(1), Decimal(position) / Decimal(params.max_position)))
    if mode in (Mode.PULL, Mode.HALT):
        return Quotes.none(f"mode {mode.value}", q)
    if fair is None or fair <= 0:
        return Quotes.none("no fair value", q)

    tick = contract.tick_size
    half_bps = params.spread_bps / 2 + extra_spread_bps
    reservation = fair * (1 - q * params.skew_bps / BPS)
    bid_px = floor_tick(reservation * (1 - half_bps / BPS), tick)
    ask_px = ceil_tick(reservation * (1 + half_bps / BPS), tick)

    # Post-only orders that would cross get rejected, so stay one tick behind the touch.
    if best_ask is not None and bid_px >= best_ask:
        bid_px = best_ask - tick
    if best_bid is not None and ask_px <= best_bid:
        ask_px = best_bid + tick

    # Delta rejects orders outside the price band published on the ticker.
    if band is not None:
        lower, upper = band
        bid_px = min(max(bid_px, ceil_tick(lower, tick)), floor_tick(upper, tick))
        ask_px = max(min(ask_px, floor_tick(upper, tick)), ceil_tick(lower, tick))

    if bid_px <= 0 or ask_px <= bid_px:
        return Quotes.none("prices collapsed after clamping", q)

    room_long = params.max_position - position  # contracts we may still buy
    room_short = params.max_position + position  # contracts we may still sell
    bid_size = min(params.order_size, max(room_long, 0))
    ask_size = min(params.order_size, max(room_short, 0))
    note = ""

    if mode is Mode.REDUCE_ONLY:
        if position > 0:
            bid_size, ask_size = 0, min(params.order_size, position)
        elif position < 0:
            bid_size, ask_size = min(params.order_size, -position), 0
        else:
            bid_size = ask_size = 0
        note = "reduce only"

    return Quotes(
        bid=QuoteSide(bid_px, bid_size) if bid_size > 0 else None,
        ask=QuoteSide(ask_px, ask_size) if ask_size > 0 else None,
        reservation=reservation,
        half_spread_bps=half_bps,
        inventory_ratio=q,
        note=note,
    )
