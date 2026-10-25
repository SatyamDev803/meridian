"""Spread experiment: run Meridian at several spreads and compare the economics.

Each run is a fresh session at one spread. At the end of a run we stop quoting, close any
inventory with a reduce-only market order (so the cost of unwinding is charged to that run),
wait for Delta's actual fees and wallet balance, then record the session's numbers.
Configs are interleaved across rounds so that no spread gets only the calm (or only the
volatile) part of the day.

    .venv/bin/python scripts/experiment.py --spreads 2,4,8,12 --minutes 12 --rounds 2

Requires a running Meridian (python -m meridian) with testnet keys. Testnet only.
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

COLUMNS = [
    ("spread", "Spread bps"),
    ("round", "Round"),
    ("minutes", "Minutes"),
    ("fills", "Fills"),
    ("fillsPerHour", "Fills per hour"),
    ("makerShare", "Maker share"),
    ("edgeAtFillBps", "Edge at fill bps"),
    ("markout5", "Markout 5s bps"),
    ("markout30", "Markout 30s bps"),
    ("adverseSelectionBps", "Adverse selection bps"),
    ("grossPnl", "Gross PnL"),
    ("fees", "Fees"),
    ("netPnl", "Net PnL (ledger)"),
    ("exchangePnl", "Net PnL (wallet)"),
    ("maxInventory", "Max inventory"),
    ("maxDrawdown", "Max drawdown"),
    ("quotingPct", "Quoting %"),
]


class Meridian:
    def __init__(self, base: str, key: str) -> None:
        self.http = httpx.Client(base_url=base, timeout=30, headers={"X-Control-Key": key})

    def state(self) -> dict:
        return self.http.get("/api/state").raise_for_status().json()

    def control(self, action: str) -> dict:
        r = self.http.post(f"/api/control/{action}")
        return {"status": r.status_code, **(r.json() if r.content else {})}

    def params(self, patch: dict) -> dict:
        return self.http.patch("/api/control/params", json=patch).raise_for_status().json()


def fmt(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.3f}" if abs(v) < 100 else f"{v:.0f}"
    return str(v)


def settle(m: Meridian, since: float, timeout: float = 45) -> dict:
    """Wait until every fill has Delta's actual fee and the wallet was read after `since`."""
    deadline = time.time() + timeout
    while True:
        st = m.state()
        perf = st["performance"]
        wallet_at = st["wallet"]["checkedAt"] or 0
        fees_done = perf["feesConfirmed"] >= perf["fills"]
        if (fees_done and wallet_at > since * 1000) or time.time() > deadline:
            return st
        time.sleep(3)


def unwind(m: Meridian) -> None:
    m.control("stop")
    time.sleep(2)
    if m.state()["position"]["contracts"] != 0:
        print("   closing leftover inventory:", m.control("flatten"))
        for _ in range(20):
            time.sleep(1)
            if m.state()["position"]["contracts"] == 0:
                break


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--key", default="", help="control key, if the server sets one")
    ap.add_argument("--spreads", default="2,4,8,12")
    ap.add_argument("--minutes", type=float, default=12)
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--size", type=int, default=2)
    ap.add_argument("--out", default="docs/experiments")
    args = ap.parse_args()

    m = Meridian(args.api, args.key)
    spreads = [s.strip() for s in args.spreads.split(",") if s.strip()]
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"spread-experiment-{stamp}.json"
    md_path = out_dir / f"spread-experiment-{stamp}.md"
    results: list[dict] = []

    def bail(*_):
        print("\nInterrupted: stopping quotes and closing inventory.")
        unwind(m)
        sys.exit(130)

    signal.signal(signal.SIGINT, bail)
    signal.signal(signal.SIGTERM, bail)

    st = m.state()
    if not st["canTrade"] and st["status"] != "running":
        print("Meridian cannot trade:", st["cannotTradeReason"])
        return 1
    if st["status"] == "halted":
        m.control("resume")
    unwind(m)
    base_params = st["params"]
    print(f"Experiment {stamp}: spreads {spreads}, {args.minutes} min each, {args.rounds} rounds")

    for rnd in range(1, args.rounds + 1):
        for spread in spreads:
            m.params({"spread_bps": spread, "order_size": args.size})
            start = m.control("start")
            if start["status"] != 200:
                print("   could not start:", start)
                return 1
            t0 = time.time()
            print(f"\n== round {rnd}, spread {spread} bps, started {time.strftime('%H:%M:%S')}")
            halted = False
            while time.time() - t0 < args.minutes * 60:
                time.sleep(15)
                s = m.state()
                p = s["performance"]
                print(
                    f"   {time.strftime('%H:%M:%S')} fills {p['fills']:3d}"
                    f"  pos {s['position']['contracts']:+3d}"
                    f"  net {p['netPnl']:+.4f}  mode {s['risk']['mode']}"
                )
                if s["status"] == "halted":
                    print("   halted:", s["haltReason"])
                    halted = True
                    break
            unwind(m)
            st = settle(m, since=time.time())
            perf = st["performance"]
            row = {
                "spread": float(spread),
                "round": rnd,
                "minutes": round((time.time() - t0) / 60, 1),
                "halted": halted,
                **{k: perf.get(k) for k in perf if k not in ("params", "markoutBps")},
                "markout5": perf["markoutBps"].get("5"),
                "markout30": perf["markoutBps"].get("30"),
                "ledgerVsExchange": perf.get("ledgerVsExchange"),
            }
            results.append(row)
            print("   result:", {k: fmt(row.get(k)) for k, _ in COLUMNS[3:]})
            write(json_path, md_path, results, args, base_params)
            if halted:
                m.control("resume")

    m.params({"spread_bps": base_params["spread_bps"], "order_size": base_params["order_size"]})
    print(f"\nDone. Results in {md_path}")
    return 0


def write(json_path: Path, md_path: Path, rows: list[dict], args, base_params: dict) -> None:
    json_path.write_text(
        json.dumps({"args": vars(args), "baseParams": base_params, "runs": rows}, indent=2)
    )
    lines = [
        "# Spread experiment",
        "",
        f"Testnet BTCUSD, {args.size} contracts per side, {args.minutes} minutes per run, "
        f"{args.rounds} interleaved rounds. Every run ends flat: leftover inventory is closed at "
        "market and that cost is charged to the run. Fees are Delta's actual commission.",
        "",
        "Edge at fill is how far inside fair value we traded. Markout is the same measure 5s and "
        "30s later. Adverse selection is edge minus the 30s markout.",
        "",
        "| " + " | ".join(label for _, label in COLUMNS) + " |",
        "|" + "---|" * len(COLUMNS),
    ]
    for r in rows:
        lines.append("| " + " | ".join(fmt(r.get(k)) for k, _ in COLUMNS) + " |")
    by_spread: dict[float, list[dict]] = {}
    for r in rows:
        by_spread.setdefault(r["spread"], []).append(r)
    lines += [
        "",
        "## Totals by spread",
        "",
        "| Spread bps | Runs | Fills | Gross PnL | Fees | Net PnL (wallet) | Net per fill |",
        "|---|---|---|---|---|---|---|",
    ]
    for spread, rs in sorted(by_spread.items()):
        fills = sum(r["fills"] for r in rs)
        gross = sum(r["grossPnl"] for r in rs)
        fees = sum(r["fees"] for r in rs)
        net = sum((r["exchangePnl"] if r["exchangePnl"] is not None else r["netPnl"]) for r in rs)
        lines.append(
            f"| {spread:g} | {len(rs)} | {fills} | {gross:+.4f} | {fees:.4f} | "
            f"{net:+.4f} | {net / fills if fills else 0:+.4f} |"
        )
    md_path.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())
