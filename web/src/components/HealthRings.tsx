"use client";

import { motion } from "motion/react";
import type { State } from "@/lib/types";
import { fmtDuration, fmtMoney, fmtSigned } from "@/lib/format";
import { Card } from "./ui/card";

// Meridian's own palette: the logo blue, indigo, and amber for money at risk.
const RINGS = [
  { key: "quoting", from: "#007AFF", to: "#5AC8FA", text: "var(--blue)" },
  { key: "inventory", from: "#5856D6", to: "#A5A3FF", text: "#5E5CE6" },
  { key: "loss", from: "#FF9500", to: "#FFCC00", text: "#E08600" },
] as const;

function Ring({ r, value, from, to, id }: { r: number; value: number; from: string; to: string; id: string }) {
  const c = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(1, value));
  return (
    <g transform="rotate(-90 100 100)">
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={from} />
          <stop offset="1" stopColor={to} />
        </linearGradient>
      </defs>
      <circle cx="100" cy="100" r={r} fill="none" stroke={from} strokeOpacity="0.14" strokeWidth="14" />
      {v > 0 && (
      <motion.circle
        cx="100"
        cy="100"
        r={r}
        fill="none"
        stroke={`url(#${id})`}
        strokeWidth="14"
        strokeLinecap="round"
        strokeDasharray={c}
        initial={{ strokeDashoffset: c }}
        animate={{ strokeDashoffset: c * (1 - v) }}
        transition={{ type: "spring", stiffness: 60, damping: 18 }}
      />
      )}
    </g>
  );
}

export function HealthRings({ state }: { state: State | null }) {
  const running = state?.status === "running";
  const quoting = running ? (state?.metrics.livelinessPct ?? 0) / 100 : 0;
  const pos = state?.position.contracts ?? 0;
  const max = state?.position.max ?? 1;
  const inventory = 1 - Math.min(1, Math.abs(pos) / max);
  const lossLimit = Number(state?.params.max_session_loss ?? 50);
  const session = state?.pnl.session ?? 0;
  const loss = 1 - Math.min(1, Math.max(0, -session) / lossLimit);
  const values = [quoting, inventory, loss];

  const rows = [
    {
      title: "Quoting",
      value: running ? `${Math.round(quoting * 100)}%` : "Not started",
      detail: running
        ? `Both quotes resting for ${Math.round(quoting * 100)}% of ${fmtDuration(state?.metrics.runningS ?? 0)}`
        : "Fills when both orders rest on Delta",
      color: RINGS[0].text,
    },
    {
      title: "Inventory headroom",
      value: `${Math.round(inventory * 100)}%`,
      detail: `Holding ${fmtSigned(pos)} of ±${max} contracts`,
      color: RINGS[1].text,
    },
    {
      title: "Loss headroom",
      value: `${Math.round(loss * 100)}%`,
      detail: `Session ${fmtMoney(session)} against a ${fmtMoney(lossLimit, false)} limit`,
      color: RINGS[2].text,
    },
  ];

  return (
    <Card title="Health" aside="Full rings mean a healthy bot">
      <div className="flex flex-col items-center gap-6 p-5 sm:flex-row lg:flex-col xl:flex-row">
        <svg viewBox="0 0 200 200" className="size-44 shrink-0" role="img" aria-label="Health rings">
          {RINGS.map((ring, i) => (
            <Ring key={ring.key} id={`ring-${ring.key}`} r={86 - i * 22} value={values[i]} from={ring.from} to={ring.to} />
          ))}
        </svg>
        <ul className="w-full space-y-4">
          {rows.map((row) => (
            <li key={row.title}>
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-[15px] font-medium">{row.title}</span>
                <span className="num font-display text-[20px] font-semibold" style={{ color: row.color }}>
                  {row.value}
                </span>
              </div>
              <div className="num text-[13px] text-label-2">{row.detail}</div>
            </li>
          ))}
        </ul>
      </div>
    </Card>
  );
}
