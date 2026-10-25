"""Risk gates. Every tick, every gate is checked; quotes rest only when all of them pass.

Each gate carries the action taken when it fails, from mildest to strictest:
    widen   keep quoting with a wider spread
    reduce  quote only the side that shrinks inventory
    pull    cancel all quotes until the gate passes again
    halt    cancel, flatten if needed, and wait for a human to resume
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal

from meridian.config import StrategyParams
from meridian.core.quoter import Mode

LIVE_SYSTEM_STATES = {"live", "api_fallback", "degraded_mode"}
SEVERITY = {"widen": 1, "reduce": 2, "pull": 3, "halt": 4}


@dataclass(frozen=True)
class RiskInputs:
    halted: bool
    halt_reason: str
    has_keys: bool
    public_ws_up: bool
    public_silence_s: float | None
    private_ws_up: bool
    private_silence_s: float | None
    mark_age_s: float | None
    ref_age_s: float | None
    book_synced: bool
    disagreement_bps: Decimal | None
    position: int
    session_pnl: Decimal
    rate_ok: bool
    rate_detail: str
    consecutive_api_errors: int
    api_cooling_down: bool
    system_status: str
    trading_status: str
    ws_silence_s: float
    mark_stale_s: float
    ref_stale_s: float
    max_api_errors: int


@dataclass(frozen=True)
class Gate:
    key: str
    label: str
    ok: bool
    action: str
    detail: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RiskDecision:
    mode: Mode
    gates: list[Gate]
    extra_spread_bps: Decimal
    flatten: bool

    @property
    def failing(self) -> list[Gate]:
        return [g for g in self.gates if not g.ok]


def _age(v: float | None) -> str:
    return "never" if v is None else f"{v:.1f}s ago"


def evaluate(inp: RiskInputs, params: StrategyParams) -> RiskDecision:
    dis = abs(inp.disagreement_bps) if inp.disagreement_bps is not None else None
    gates = [
        Gate(
            "not_halted",
            "Kill switch",
            not inp.halted,
            "halt",
            inp.halt_reason if inp.halted else "armed",
        ),
        Gate(
            "delta_public",
            "Delta market feed",
            inp.public_ws_up
            and inp.public_silence_s is not None
            and inp.public_silence_s < inp.ws_silence_s,
            "pull",
            ("connected" if inp.public_ws_up else "down")
            + f", last message {_age(inp.public_silence_s)}",
        ),
        Gate(
            "delta_private",
            "Delta account feed",
            inp.has_keys and inp.private_ws_up,
            "pull",
            "authenticated"
            if inp.private_ws_up
            else ("no API keys" if not inp.has_keys else "not authenticated"),
        ),
        Gate(
            "mark_fresh",
            "Mark price fresh",
            inp.mark_age_s is not None and inp.mark_age_s < inp.mark_stale_s,
            "pull",
            f"updated {_age(inp.mark_age_s)}",
        ),
        Gate(
            "book_synced",
            "Order book in sync",
            inp.book_synced,
            "pull",
            "sequence and checksum verified" if inp.book_synced else "resyncing",
        ),
        Gate(
            "ref_fresh",
            "Binance reference fresh",
            inp.ref_age_s is not None and inp.ref_age_s < inp.ref_stale_s,
            "pull",
            f"updated {_age(inp.ref_age_s)}",
        ),
        Gate(
            "ref_agrees",
            "Prices agree",
            dis is not None and dis <= params.guard_bps,
            "pull" if dis is None or dis > params.guard_bps else "widen",
            "waiting for both prices"
            if dis is None
            else f"{dis:.1f} bps apart, limit {params.guard_bps} bps",
        ),
        Gate(
            "inventory_ok",
            "Inventory in limits",
            abs(inp.position) < params.max_position,
            "reduce",
            f"{inp.position:+d} of ±{params.max_position} contracts",
        ),
        Gate(
            "loss_ok",
            "Session loss limit",
            inp.session_pnl > -params.max_session_loss,
            "halt",
            f"PnL {inp.session_pnl:+.2f} USD, limit -{params.max_session_loss} USD",
        ),
        Gate("rate_ok", "Rate limit headroom", inp.rate_ok, "pull", inp.rate_detail),
        Gate(
            "api_healthy",
            "Exchange API healthy",
            inp.consecutive_api_errors < inp.max_api_errors and not inp.api_cooling_down,
            "pull",
            "cooling down after errors"
            if inp.api_cooling_down
            else f"{inp.consecutive_api_errors} consecutive errors",
        ),
        Gate(
            "exchange_live",
            "Exchange operational",
            inp.system_status in LIVE_SYSTEM_STATES and inp.trading_status == "operational",
            "pull",
            f"system {inp.system_status}, market {inp.trading_status}",
        ),
    ]

    worst = max((SEVERITY[g.action] for g in gates if not g.ok), default=0)
    if worst >= SEVERITY["halt"]:
        mode = Mode.HALT
    elif worst >= SEVERITY["pull"]:
        mode = Mode.PULL
    elif worst >= SEVERITY["reduce"]:
        mode = Mode.REDUCE_ONLY
    else:
        mode = Mode.QUOTE

    extra = Decimal(0)
    if dis is not None and params.warn_bps < dis <= params.guard_bps:
        extra = dis - params.warn_bps
        # Inside the warn band the gate reads as passing with a wider spread.
        gates = [
            Gate(g.key, g.label, True, "widen", f"{g.detail}, spread widened {extra:.1f} bps")
            if g.key == "ref_agrees"
            else g
            for g in gates
        ]

    loss_breached = not next(g for g in gates if g.key == "loss_ok").ok
    return RiskDecision(
        mode=mode,
        gates=gates,
        extra_spread_bps=extra,
        flatten=loss_breached and inp.position != 0,
    )
