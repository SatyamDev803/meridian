"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import type { PricePoint, State } from "@/lib/types";
import { cn, fmtBps, fmtPrice } from "@/lib/format";
import { PriceChart } from "./PriceChart";

function useTick(value: number | null) {
  const prev = useRef(value);
  const [dir, setDir] = useState<0 | 1 | -1>(0);
  useEffect(() => {
    if (value != null && prev.current != null && value !== prev.current) {
      setDir(value > prev.current ? 1 : -1);
      const t = setTimeout(() => setDir(0), 900);
      prev.current = value;
      return () => clearTimeout(t);
    }
    prev.current = value;
  }, [value]);
  return dir;
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="min-w-0">
      <div className="text-[13px] text-label-2">{label}</div>
      <div className="num truncate text-[17px] font-semibold tracking-[-0.01em]" title={hint}>
        {value}
      </div>
    </div>
  );
}

function QuotePill({ side, price, size, live }: { side: "bid" | "ask"; price: number | null; size: number; live: boolean }) {
  const bid = side === "bid";
  return (
    <div
      className={cn(
        "flex min-w-0 flex-1 items-center justify-between gap-3 rounded-2xl px-4 py-3",
        bid ? "bg-[color-mix(in_srgb,var(--green)_12%,transparent)]" : "bg-[color-mix(in_srgb,var(--red)_12%,transparent)]",
      )}
    >
      <div>
        <div className={cn("text-[13px] font-medium", bid ? "text-green" : "text-red")}>
          {bid ? "We buy at" : "We sell at"}
        </div>
        <div className="num font-display text-[22px] font-semibold tracking-[-0.02em]">
          {price == null ? "Off" : fmtPrice(price)}
        </div>
      </div>
      <div className="text-right text-[13px] text-label-2">
        <div className="num">{price == null ? "No order" : `${size} contracts`}</div>
        <div>{live ? "Resting on Delta" : "Preview"}</div>
      </div>
    </div>
  );
}

export function Hero({ state, points }: { state: State | null; points: PricePoint[] }) {
  const m = state?.market;
  const q = state?.quotes;
  const fair = m?.fair ?? null;
  const dir = useTick(fair);
  const live = state?.status === "running";
  const liveBuy = !!state?.orders?.live.buy?.order_id;
  const liveSell = !!state?.orders?.live.sell?.order_id;

  return (
    <section className="overflow-hidden rounded-[22px] bg-surface shadow-card">
      <div className="flex flex-col gap-6 p-5 sm:p-6 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="text-[15px] text-label-2">Fair price, {state?.symbol ?? "BTCUSD"}</div>
          <div className="relative">
            <AnimatePresence initial={false}>
              <motion.div
                key={fair == null ? "none" : "price"}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                className="num flex items-baseline gap-3 font-display text-[56px] font-semibold leading-[1.05] tracking-[-0.045em] sm:text-[72px]"
              >
                {fair == null ? "Waiting for Delta" : fmtPrice(fair)}
                {fair != null && (
                  <span
                    aria-hidden="true"
                    className={cn(
                      "text-[28px] transition-opacity duration-500",
                      dir === 0 ? "opacity-0" : "opacity-100",
                      dir === -1 ? "text-red" : "text-green",
                    )}
                  >
                    {dir === -1 ? "▼" : "▲"}
                  </span>
                )}
              </motion.div>
            </AnimatePresence>
          </div>
          <p className="mt-1 max-w-[52ch] text-[15px] text-label-2">
            Delta&apos;s mark price, nudged by how far Binance has moved since the last mark.
            Our quotes lean away from inventory so we drift back to flat.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-x-8 gap-y-4 sm:grid-cols-4 lg:min-w-[520px]">
          <Stat label="Delta mark" value={fmtPrice(m?.mark)} />
          <Stat label="Binance" value={fmtPrice(m?.ref)} />
          <Stat label="Learned basis" value={fmtBps(m?.basisBps)} hint="Normal gap between Binance and Delta" />
          <Stat label="Disagreement" value={fmtBps(m?.disagreementBps == null ? null : Math.abs(m.disagreementBps))} />
        </div>
      </div>

      <div className="flex flex-col gap-3 px-5 sm:flex-row sm:px-6">
        <QuotePill side="bid" price={q?.bid ?? null} size={q?.bidSize ?? 0} live={live && liveBuy} />
        <QuotePill side="ask" price={q?.ask ?? null} size={q?.askSize ?? 0} live={live && liveSell} />
      </div>
      {state && !live && (
        <p className="px-5 pt-3 text-[13px] text-label-2 sm:px-6">
          {state.status === "halted"
            ? `Halted: ${state.haltReason}. Resume when you are ready.`
            : state.canTrade
              ? "These are the prices Meridian would quote. Start quoting to place them on Delta."
              : state.cannotTradeReason}
        </p>
      )}

      <div className="mt-2 px-2 pb-3 sm:px-3">
        <PriceChart points={points} />
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-1 px-5 pb-5 text-[12px] text-label-2 sm:px-6">
        <Legend color="var(--blue)" label="Fair price" thick />
        <Legend color="var(--green)" label="Our bid" dashed />
        <Legend color="var(--red)" label="Our ask" dashed />
        <Legend color="var(--teal)" label="Binance" dotted />
        <Legend color="var(--label-3)" label="Delta best bid and ask" />
        <span className="num ml-auto">Book spread {fmtBps(m?.spreadBps, 2)}</span>
      </div>
    </section>
  );
}

function Legend({ color, label, thick, dashed, dotted }: { color: string; label: string; thick?: boolean; dashed?: boolean; dotted?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className="inline-block w-4"
        style={{
          borderTop: `${thick ? 3 : 2}px ${dashed ? "dashed" : dotted ? "dotted" : "solid"} ${color}`,
        }}
      />
      {label}
    </span>
  );
}
