"use client";

import { useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";

// A toy version of the strategy for the landing hero: a wandering fair price, our bid and ask
// around it, trades that hit them, and the quotes leaning away from the inventory that builds up.
// Simulated on purpose. The live numbers are in the dashboard below.

const W = 560;
const H = 260;
const N = 140; // points across the chart
const STEP_MS = 70;
const HALF = 7; // half spread, in chart units
const LEAN = 2.2; // lean per contract held
const MAX_INV = 4;

type Fill = { x: number; y: number; side: "buy" | "sell"; age: number };

function makeSim() {
  let fair = H / 2;
  let vel = 0;
  let inv = 0;
  const fairs: number[] = [];
  const leans: number[] = [];
  let fills: Fill[] = [];

  function step() {
    // Mean-reverting random walk with a little momentum.
    vel = vel * 0.85 + (Math.random() - 0.5) * 2.6 + (H / 2 - fair) * 0.004;
    fair = Math.min(H - 40, Math.max(40, fair + vel));
    const lean = inv * LEAN;
    const bid = fair + HALF + lean; // screen y grows downward, so the bid sits below
    const ask = fair - HALF + lean;
    const trade = fair + (Math.random() - 0.5) * 30;
    if (trade >= bid && inv < MAX_INV) {
      inv += 1;
      fills.push({ x: fairs.length, y: bid, side: "buy", age: 0 });
    } else if (trade <= ask && inv > -MAX_INV) {
      inv -= 1;
      fills.push({ x: fairs.length, y: ask, side: "sell", age: 0 });
    }
    // Inventory slowly drifts back toward flat, as the lean intends.
    if (inv !== 0 && Math.random() < 0.04) inv -= Math.sign(inv);
    fairs.push(fair);
    leans.push(inv * LEAN);
    if (fairs.length > N) {
      fairs.shift();
      leans.shift();
      fills = fills.map((f) => ({ ...f, x: f.x - 1, age: f.age + 1 })).filter((f) => f.x >= 0);
    } else {
      fills = fills.map((f) => ({ ...f, age: f.age + 1 }));
    }
  }

  for (let i = 0; i < N; i++) step();
  // Visible y range, eased so the chart zooms smoothly instead of jumping.
  let lo = Math.min(...fairs) - HALF * 3;
  let hi = Math.max(...fairs) + HALF * 3;
  return {
    step,
    get: () => {
      const tLo = Math.min(...fairs.map((f, i) => f - HALF + leans[i])) - HALF;
      const tHi = Math.max(...fairs.map((f, i) => f + HALF + leans[i])) + HALF;
      lo += (tLo - lo) * 0.15;
      hi += (tHi - hi) * 0.15;
      const sy = (v: number) => 24 + ((v - lo) / Math.max(hi - lo, 1)) * (H - 48);
      return { fairs, leans, fills, inv, sy };
    },
  };
}

function path(values: number[], offset: (i: number) => number, sy: (v: number) => number) {
  const dx = W / (N - 1);
  return values.map((v, i) => `${i ? "L" : "M"}${(i * dx).toFixed(1)},${sy(v + offset(i)).toFixed(1)}`).join("");
}

export function QuoteSim() {
  const reduce = useReducedMotion();
  const sim = useRef<ReturnType<typeof makeSim> | null>(null);
  const [frame, setFrame] = useState(0);

  // Random numbers only after mount, so the prerendered page and the browser agree.
  useEffect(() => {
    sim.current ??= makeSim();
    setFrame((f) => f + 1);
    if (reduce) return;
    const id = setInterval(() => {
      sim.current!.step();
      setFrame((f) => f + 1);
    }, STEP_MS);
    return () => clearInterval(id);
  }, [reduce]);

  if (!sim.current || frame === 0) {
    return <figure className="aspect-[630/330] rounded-[22px] bg-surface shadow-card" aria-hidden="true" />;
  }
  const { fairs, leans, fills, inv, sy } = sim.current.get();
  const bidPath = path(fairs, (i) => HALF + leans[i], sy);
  const askPath = path(fairs, (i) => -HALF + leans[i], sy);
  // The shaded spread: along the ask, then back along the bid.
  const bidBack = fairs
    .map((v, i) => `L${((i * W) / (N - 1)).toFixed(1)},${sy(v + HALF + leans[i]).toFixed(1)}`)
    .reverse()
    .join("");
  const band = `${askPath}${bidBack}Z`;
  const last = fairs.length - 1;
  const lastLean = leans[last];
  const yFair = sy(fairs[last]);
  const yAsk = sy(fairs[last] - HALF + lastLean);
  const yBid = sy(fairs[last] + HALF + lastLean);

  return (
    <figure className="relative overflow-hidden rounded-[22px] bg-surface p-4 shadow-card sm:p-5">
      <figcaption className="flex items-baseline justify-between gap-3 text-[13px]">
        <span className="font-medium">How Meridian quotes</span>
        <span className="text-label-2">Simulation. Live numbers are below.</span>
      </figcaption>
      <svg viewBox={`0 0 ${W + 70} ${H}`} className="mt-3 h-auto max-h-[46vh] w-full" role="img" aria-label="Animated illustration: a fair price line with our buy and sell quotes around it, leaning away from inventory as trades fill.">
        <defs>
          <clipPath id="sim-clip">
            <rect width={W} height={H} />
          </clipPath>
        </defs>
        <g clipPath="url(#sim-clip)">
          <path d={band} fill="var(--blue)" opacity={0.08} />
          <path d={bidPath} fill="none" stroke="var(--green)" strokeWidth={2} strokeDasharray="5 4" />
          <path d={askPath} fill="none" stroke="var(--red)" strokeWidth={2} strokeDasharray="5 4" />
          <path d={path(fairs, () => 0, sy)} fill="none" stroke="var(--blue)" strokeWidth={3} strokeLinejoin="round" strokeLinecap="round" />
          {fills.map((f, i) => (
            <circle
              key={`${f.side}-${i}-${f.age}`}
              cx={(f.x * W) / (N - 1)}
              cy={sy(f.y)}
              r={f.age < 4 ? 7 - f.age : 4}
              fill={f.side === "buy" ? "var(--green)" : "var(--red)"}
              opacity={Math.max(0.25, 1 - f.age / 80)}
            />
          ))}
        </g>
        <circle cx={W} cy={yFair} r={5} fill="var(--blue)" />
        <circle cx={W} cy={yFair} r={11} fill="var(--blue)" opacity={0.18}>
          {!reduce && <animate attributeName="r" values="6;14;6" dur="1.6s" repeatCount="indefinite" />}
        </circle>
        <text x={W + 10} y={Math.min(yAsk, yFair - 14) - 2} fontSize={13} fill="var(--red)">Ask</text>
        <text x={W + 10} y={yFair + 4} fontSize={13} fontWeight={600} fill="var(--blue)">Fair</text>
        <text x={W + 10} y={Math.max(yBid, yFair + 14) + 14} fontSize={13} fill="var(--green)">Bid</text>
      </svg>
      <div className="mt-3 flex items-center gap-3 text-[13px]">
        <span className="text-label-2">Holding</span>
        <div className="relative h-1.5 flex-1 rounded-full bg-fill">
          <span className="absolute inset-y-[-3px] left-1/2 w-px bg-label-3" />
          <span
            className="absolute top-0 h-full rounded-full transition-all duration-300"
            style={{
              left: inv >= 0 ? "50%" : `${50 + (inv / MAX_INV) * 50}%`,
              width: `${(Math.abs(inv) / MAX_INV) * 50}%`,
              background: inv >= 0 ? "var(--green)" : "var(--red)",
            }}
          />
        </div>
        <span className="num shrink-0 whitespace-nowrap text-right">
          {inv === 0 ? "Flat, quotes centred" : inv > 0 ? `Long ${inv}, quotes lean down` : `Short ${-inv}, quotes lean up`}
        </span>
      </div>
    </figure>
  );
}
