"use client";

import type { State } from "@/lib/types";
import { cn, fmtMoney } from "@/lib/format";
import { Card } from "./ui/card";

function bps(v: number | null | undefined) {
  if (v == null) return "-";
  const s = Math.abs(v).toFixed(2);
  return v > 0.005 ? `+${s} bps` : v < -0.005 ? `\u2212${s} bps` : `${s} bps`;
}

function tone(v: number | null | undefined) {
  if (v == null || Math.abs(v) < 0.005) return "";
  return v > 0 ? "text-green" : "text-red";
}

export function Economics({ state }: { state: State | null }) {
  const p = state?.performance;
  const pending = p ? p.fills - p.feesConfirmed : 0;
  const diff = p?.ledgerVsExchange;

  return (
    <Card title="Where the PnL comes from" aside={p?.fills ? `${p.fills} fills this session` : "No fills this session"}>
      <div className="grid gap-5 p-5 md:grid-cols-2">
        <section>
          <h3 className="text-[13px] text-label-2">Execution quality</h3>
          <dl className="mt-2 divide-y divide-hairline rounded-2xl bg-surface-2 text-[15px]">
            <Row label="Edge at fill" hint="How far inside fair value we traded" value={bps(p?.edgeAtFillBps)} className={tone(p?.edgeAtFillBps)} />
            <Row label="5 seconds later" hint="Same measure against where fair value went" value={bps(p?.markoutBps?.["5"])} className={tone(p?.markoutBps?.["5"])} />
            <Row label="30 seconds later" value={bps(p?.markoutBps?.["30"])} className={tone(p?.markoutBps?.["30"])} />
            <Row label="Lost to adverse selection" hint="Edge the market took back within 30s" value={bps(p?.adverseSelectionBps)} />
          </dl>
        </section>
        <section>
          <h3 className="text-[13px] text-label-2">Profit and loss</h3>
          <dl className="mt-2 divide-y divide-hairline rounded-2xl bg-surface-2 text-[15px]">
            <Row label="Spread captured" hint="Before fees" value={fmtMoney(p?.grossPnl)} className={tone(p?.grossPnl)} />
            <Row
              label="Fees"
              hint={p?.fills ? (pending ? `${pending} awaiting Delta's figure` : "Confirmed by Delta, taxes included") : undefined}
              value={fmtMoney(p ? -p.fees : null)}
            />
            <Row label="Net, Meridian ledger" value={fmtMoney(p?.netPnl)} className={tone(p?.netPnl)} />
            <Row
              label="Net, Delta wallet"
              hint={diff == null ? "Read every 10 seconds" : Math.abs(diff) < 0.005 ? "Matches the ledger" : `Ledger differs by ${fmtMoney(diff)}`}
              value={fmtMoney(p?.exchangePnl)}
              className={cn("font-semibold", tone(p?.exchangePnl))}
            />
          </dl>
        </section>
      </div>
    </Card>
  );
}

function Row({ label, hint, value, className }: { label: string; hint?: string; value: string; className?: string }) {
  return (
    <div className="flex items-center justify-between gap-4 px-3 py-2.5">
      <div className="min-w-0">
        <dt>{label}</dt>
        {hint && <div className="text-[12px] text-label-2">{hint}</div>}
      </div>
      <dd className={cn("num shrink-0 font-medium", className)}>{value}</dd>
    </div>
  );
}
