"""Decision log: why every order was placed, amended or cancelled, and why quoting paused.

Each record carries the exact inputs the strategy tick used: the same FairEstimate,
RiskDecision, Quotes and StrategyParams objects passed to the quoter and the order manager.
Nothing is reconstructed afterwards. The log is read-only: trading never reads it back.
"""

from __future__ import annotations

import itertools
import time
from collections import deque
from decimal import Decimal
from typing import Any

from meridian.config import StrategyParams
from meridian.core.fair_value import FairEstimate
from meridian.core.oms import Action
from meridian.core.quoter import Quotes
from meridian.core.risk import RiskDecision

TARGET_POSITION = 0  # Meridian always leans back toward flat


def num(x: Decimal | None) -> float | None:
    return None if x is None else float(x)


def snapshot_inputs(
    *,
    est: FairEstimate,
    decision: RiskDecision,
    quotes: Quotes,
    params: StrategyParams,
    position: int,
    best_bid: Decimal | None,
    best_ask: Decimal | None,
    band: tuple[Decimal, Decimal] | None,
    preview: bool,
) -> dict[str, Any]:
    skew_applied = quotes.inventory_ratio * params.skew_bps
    return {
        "capturedAt": time.time() * 1000,  # the strategy tick these values come from
        "reference": {
            "fair": num(est.fair),
            "deltaMark": num(est.mark),
            "binanceMid": num(est.ref_mid),
            "drift": num(est.drift),
            "basisBps": num(est.basis_bps),
            "disagreementBps": num(est.disagreement_bps),
        },
        "inventory": {
            "position": position,
            "target": TARGET_POSITION,
            "max": params.max_position,
            "ratio": num(quotes.inventory_ratio),
        },
        "pricing": {
            "spreadBps": num(params.spread_bps),
            "halfSpreadAppliedBps": num(quotes.half_spread_bps),
            "skewBps": num(params.skew_bps),
            "skewAppliedBps": num(skew_applied),
            "reservation": num(quotes.reservation),
            "disagreementWideningBps": num(decision.extra_spread_bps),
            # Meridian has no volatility model. Recorded as zero so the gap is visible.
            "volatilityAdjustmentBps": 0.0,
            "volatilityModel": "none",
            "requoteBps": num(params.requote_bps),
        },
        "book": {
            "bestBid": num(best_bid),
            "bestAsk": num(best_ask),
            "band": [num(band[0]), num(band[1])] if band else None,
        },
        "risk": {
            "mode": decision.mode.value,
            "gates": [g.as_dict() for g in decision.gates],
            "failing": [g.label for g in decision.failing if g.action != "widen"],
        },
        "final": {
            "bid": num(quotes.bid.price) if quotes.bid else None,
            "bidSize": quotes.bid.size if quotes.bid else 0,
            "ask": num(quotes.ask.price) if quotes.ask else None,
            "askSize": quotes.ask.size if quotes.ask else 0,
            "note": quotes.note,
            "preview": preview,
        },
    }


class DecisionLog:
    def __init__(self, maxlen: int = 500) -> None:
        self.records: deque[dict] = deque(maxlen=maxlen)
        self._ids = itertools.count(1)

    def _add(self, kind: str, summary: str, inputs: dict | None, **extra: Any) -> dict:
        rec = {
            "id": next(self._ids),
            "ts": time.time() * 1000,
            "kind": kind,
            "summary": summary,
            "inputs": inputs,
            **extra,
        }
        self.records.appendleft(rec)
        return rec

    def orders(self, inputs: dict, results: list[tuple[Action, str]]) -> dict:
        actions = [
            {
                "kind": a.kind,
                "side": a.side,
                "price": num(a.price),
                "prevPrice": num(a.prev_price),
                "size": a.size,
                "reason": a.reason,
                "outcome": outcome,
            }
            for a, outcome in results
        ]
        verbs = {"place": "Placed", "edit": "Amended", "cancel": "Cancelled"}
        summary = ", ".join(f"{verbs[a['kind']]} {a['side']}" for a in actions)
        return self._add("orders", summary, inputs, actions=actions)

    def pause(self, inputs: dict, mode: str, gates: list[dict]) -> dict:
        reasons = [f"{g['label']}: {g['detail']}" for g in gates]
        verb = {"pull": "Quotes pulled", "reduce_only": "Reducing only", "halt": "Halted"}
        return self._add(
            "pause",
            f"{verb.get(mode, mode)}: {'; '.join(reasons)}",
            inputs,
            mode=mode,
            reasons=reasons,
        )

    def resume(self, inputs: dict) -> dict:
        return self._add("resume", "All checks passed. Quoting both sides again.", inputs)

    def cancel_all(self, inputs: dict | None, reason: str, ok: bool, leftovers: int) -> dict:
        tail = "" if ok else " Delta did not confirm."
        if leftovers:
            tail += f" {leftovers} orders survived and were cancelled one by one."
        return self._add(
            "cancel_all",
            f"Cancelled every order: {reason}.{tail}",
            inputs,
            reason=reason,
            ok=ok,
            leftovers=leftovers,
        )

    def list(self, limit: int = 100, kind: str | None = None) -> list[dict]:
        out = [r for r in self.records if kind is None or r["kind"] == kind]
        return out[:limit]
