"use client";

import { Area, AreaChart, ReferenceLine, ResponsiveContainer, Tooltip, YAxis } from "recharts";
import type { PnlPoint, State } from "@/lib/types";
import { cn, fmtMoney, fmtPrice, fmtSigned, fmtTime } from "@/lib/format";
import { Card } from "./ui/card";

export function PositionCard({ state, pnl }: { state: State | null; pnl: PnlPoint[] }) {
  const p = state?.pnl;
  const pos = state?.position;
  const session = p?.session ?? 0;
  const ratio = state?.quotes.inventoryRatio ?? 0;
  const tone = session > 0.004 ? "text-green" : session < -0.004 ? "text-red" : "text-label";
  const data = pnl.slice(-300);

  return (
    <Card title="Position and PnL" aside={p?.fills ? `${p.fills} fills since Meridian started` : "No fills yet"}>
      <div className="grid gap-5 p-5 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <div className="space-y-5">
          <div>
            <div className="text-[13px] text-label-2">Session PnL</div>
            <div className={cn("num font-display text-[40px] font-semibold leading-tight tracking-[-0.035em]", tone)}>
              {fmtMoney(session)}
            </div>
          </div>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-[13px]">
            <Item label="Realized" value={fmtMoney(p?.realized)} />
            <Item label="Unrealized" value={fmtMoney(p?.unrealized)} />
            <Item label="Fees paid" value={fmtMoney(p?.fees, false)} />
            <Item label="Max drawdown" value={fmtMoney(p?.maxDrawdown, false)} />
            <Item label="Maker share" value={p?.makerRatio == null ? "-" : `${Math.round(p.makerRatio * 100)}%`} />
            <Item label="Volume" value={fmtMoney(p?.volumeUsd, false)} />
          </dl>
        </div>
        <div className="flex min-w-0 flex-col gap-4">
          <div>
            <div className="flex items-baseline justify-between text-[13px]">
              <span className="text-label-2">Inventory</span>
              <span className="num font-medium">
                {fmtSigned(pos?.contracts ?? 0)} contracts
                {pos?.avgPrice ? <span className="text-label-2"> at {fmtPrice(pos.avgPrice)}</span> : null}
              </span>
            </div>
            <InventoryBar ratio={ratio} />
            <div className="mt-1 flex justify-between text-[12px] text-label-2">
              <span>Short limit</span>
              <span>Flat</span>
              <span>Long limit</span>
            </div>
          </div>
          <div className="h-[120px] min-w-0">
            {data.length > 1 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
                  <defs>
                    <linearGradient id="pnlFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0" stopColor="var(--blue)" stopOpacity={0.28} />
                      <stop offset="1" stopColor="var(--blue)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <YAxis hide domain={["auto", "auto"]} />
                  <ReferenceLine y={0} stroke="var(--hairline)" />
                  <Tooltip
                    cursor={{ stroke: "var(--hairline)" }}
                    contentStyle={{
                      background: "var(--surface)",
                      border: "1px solid var(--hairline)",
                      borderRadius: 12,
                      fontSize: 12,
                    }}
                    labelFormatter={(_, items) => (items?.[0] ? fmtTime(items[0].payload.t) : "")}
                    formatter={(v) => [fmtMoney(Number(v)), "Session PnL"]}
                  />
                  <Area
                    type="monotone"
                    dataKey="total"
                    stroke="var(--blue)"
                    strokeWidth={2}
                    fill="url(#pnlFill)"
                    isAnimationActive={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="grid h-full place-items-center rounded-2xl bg-fill text-[13px] text-label-2">
                PnL history appears once Meridian is running.
              </div>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}

function Item({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-label-2">{label}</dt>
      <dd className="num text-[15px] font-semibold">{value}</dd>
    </div>
  );
}

function InventoryBar({ ratio }: { ratio: number }) {
  const pct = Math.max(-1, Math.min(1, ratio));
  const width = Math.abs(pct) * 50;
  return (
    <div className="relative mt-2 h-2.5 rounded-full bg-fill" aria-hidden="true">
      <div className="absolute inset-y-0 left-1/2 w-px bg-label-3" />
      <div
        className={cn(
          "absolute inset-y-0 rounded-full transition-all duration-500",
          pct >= 0 ? "bg-green" : "bg-red",
        )}
        style={pct >= 0 ? { left: "50%", width: `${width}%` } : { right: "50%", width: `${width}%` }}
      />
    </div>
  );
}
