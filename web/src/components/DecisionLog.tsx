"use client";

import { ChevronRight, CircleSlash, Pause, Pencil, Play, Plus, X, type LucideIcon } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import type { Decision, DecisionAction, DecisionInputs } from "@/lib/types";
import { cn, fmtBps, fmtPrice, fmtTime } from "@/lib/format";
import { Card } from "./ui/card";

type Filter = "all" | "orders" | "safety";

const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "orders", label: "Orders" },
  { value: "safety", label: "Safety pauses" },
];

const KIND: Record<Decision["kind"], { icon: LucideIcon; tint: string; title: string }> = {
  orders: { icon: Pencil, tint: "bg-blue", title: "Order decision" },
  pause: { icon: Pause, tint: "bg-orange", title: "Safety pause" },
  resume: { icon: Play, tint: "bg-green", title: "Resumed" },
  cancel_all: { icon: CircleSlash, tint: "bg-red", title: "Cancelled everything" },
};

const ACTION: Record<DecisionAction["kind"], { icon: LucideIcon; verb: string }> = {
  place: { icon: Plus, verb: "Placed" },
  edit: { icon: Pencil, verb: "Amended" },
  cancel: { icon: X, verb: "Cancelled" },
};

export function DecisionLog({ decisions, available }: { decisions: Decision[]; available: boolean }) {
  const [filter, setFilter] = useState<Filter>("all");
  const [open, setOpen] = useState<number | null>(null);
  const shown = decisions
    .filter((d) =>
      filter === "all" ? true : filter === "orders" ? d.kind === "orders" : d.kind !== "orders",
    )
    .slice(0, 60);

  return (
    <Card
      title="Why Meridian did that"
      aside={
        <div role="radiogroup" aria-label="Filter decisions" className="flex rounded-full bg-fill p-[3px]">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              role="radio"
              aria-checked={filter === f.value}
              onClick={() => setFilter(f.value)}
              className={cn(
                "rounded-full px-3 py-1 text-[13px] transition-colors",
                filter === f.value ? "bg-segment text-label shadow-[0_1px_3px_rgba(0,0,0,0.12)]" : "text-label-2",
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
      }
    >
      <p className="px-5 pt-1 text-[13px] text-label-2">
        Every place, amend, cancel and pause, with the exact numbers the strategy used at that moment.
      </p>
      <ol className="mt-3 max-h-[560px] overflow-y-auto px-3 pb-3">
        {shown.map((d) => (
          <DecisionRow key={d.id} d={d} open={open === d.id} onToggle={() => setOpen(open === d.id ? null : d.id)} />
        ))}
        {!shown.length && (
          <li className="px-2 py-10 text-center text-[15px] text-label-2">
            {available
              ? filter === "safety"
                ? "No safety pauses yet."
                : "No decisions yet. Start quoting to see each one explained."
              : "This server is running an older build. Restart Meridian to record decisions."}
          </li>
        )}
      </ol>
    </Card>
  );
}

function DecisionRow({ d, open, onToggle }: { d: Decision; open: boolean; onToggle: () => void }) {
  const k = KIND[d.kind];
  const Icon = k.icon;
  return (
    <li className="rounded-2xl">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-start gap-3 rounded-2xl px-2 py-2.5 text-left transition-colors hover:bg-fill"
      >
        <span className={cn("mt-0.5 grid size-7 shrink-0 place-items-center rounded-full text-white", k.tint)}>
          <Icon className="size-3.5" strokeWidth={2.6} aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          {d.kind === "orders" && d.actions ? (
            <div className="space-y-0.5">
              {d.actions.map((a, i) => (
                <ActionLine key={i} a={a} />
              ))}
            </div>
          ) : (
            <p className="text-[14px] leading-snug">{d.summary}</p>
          )}
          <time className="num text-[12px] text-label-2">{fmtTime(d.ts)}</time>
        </div>
        <ChevronRight
          className={cn("mt-1 size-4 shrink-0 text-label-3 transition-transform", open && "rotate-90")}
          aria-hidden="true"
        />
      </button>
      <AnimatePresence initial={false}>
        {open && d.inputs && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ type: "spring", stiffness: 380, damping: 36 }}
            className="overflow-hidden"
          >
            <Details d={d} inputs={d.inputs} />
          </motion.div>
        )}
      </AnimatePresence>
    </li>
  );
}

function ActionLine({ a }: { a: DecisionAction }) {
  const A = ACTION[a.kind];
  const side = a.side === "buy" ? "bid" : "ask";
  const failed = !a.outcome.startsWith("accepted");
  const price =
    a.kind === "edit"
      ? `${fmtPrice(a.prevPrice)} to ${fmtPrice(a.price)}`
      : a.kind === "place"
        ? `${fmtPrice(a.price)}, ${a.size} contracts`
        : fmtPrice(a.prevPrice);
  return (
    <p className="text-[14px] leading-snug">
      <span className="font-medium">
        {A.verb} {side}
      </span>{" "}
      <span className="num">{price}</span>
      <span className="text-label-2">. {capitalise(a.reason)}.</span>
      {failed && <span className="text-red"> {capitalise(a.outcome)}.</span>}
    </p>
  );
}

function Details({ d, inputs: i }: { d: Decision; inputs: DecisionInputs }) {
  const failing = new Set(i.risk.failing);
  return (
    <div className="mx-2 mb-3 space-y-3 rounded-2xl bg-surface-2 p-4 text-[13px]">
      <p className="text-[12px] text-label-2">
        Strategy state as of the tick at <span className="num">{fmtTime(i.capturedAt)}</span>
        {d.kind === "cancel_all" ? ", the last tick before this cancel." : "."}
      </p>
      {d.kind === "pause" && d.reasons && (
        <Section title="Why quoting paused">
          <ul className="space-y-1">
            {d.reasons.map((r) => (
              <li key={r} className="text-red">
                {r}
              </li>
            ))}
          </ul>
        </Section>
      )}
      {d.actions && (
        <Section title="Exchange response">
          <ul className="space-y-1">
            {d.actions.map((a, n) => (
              <li key={n} className="num">
                {ACTION[a.kind].verb} {a.side === "buy" ? "bid" : "ask"}: {a.outcome}
              </li>
            ))}
          </ul>
        </Section>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <Section title="Reference price">
          <Grid
            rows={[
              ["Fair value", fmtPrice(i.reference.fair)],
              ["Delta mark", fmtPrice(i.reference.deltaMark)],
              ["Binance mid", fmtPrice(i.reference.binanceMid)],
              ["Drift since mark", signed(i.reference.drift)],
              ["Learned basis", fmtBps(i.reference.basisBps, 2)],
              ["Disagreement", fmtBps(i.reference.disagreementBps, 2)],
            ]}
          />
        </Section>
        <Section title="Inventory">
          <Grid
            rows={[
              ["Current", `${i.inventory.position} contracts`],
              ["Target", `${i.inventory.target} contracts`],
              ["Limit", `±${i.inventory.max} contracts`],
              ["Fullness", i.inventory.ratio == null ? "-" : `${Math.round(i.inventory.ratio * 100)}%`],
            ]}
          />
        </Section>
        <Section title="Pricing">
          <Grid
            rows={[
              ["Configured spread", fmtBps(i.pricing.spreadBps, 2)],
              ["Half spread applied", fmtBps(i.pricing.halfSpreadAppliedBps, 2)],
              ["Inventory skew", `${fmtBps(i.pricing.skewAppliedBps, 2)} of ${fmtBps(i.pricing.skewBps, 0)}`],
              ["Reservation price", fmtPrice(i.pricing.reservation)],
              ["Disagreement widening", fmtBps(i.pricing.disagreementWideningBps, 2)],
              [
                "Volatility adjustment",
                i.pricing.volatilityModel === "none"
                  ? `${fmtBps(i.pricing.volatilityAdjustmentBps, 0)}, not modelled`
                  : fmtBps(i.pricing.volatilityAdjustmentBps, 2),
              ],
            ]}
          />
        </Section>
        <Section title="Final quote">
          <Grid
            rows={[
              ["Bid", i.final.bid == null ? "None" : `${fmtPrice(i.final.bid)} for ${i.final.bidSize}`],
              ["Ask", i.final.ask == null ? "None" : `${fmtPrice(i.final.ask)} for ${i.final.askSize}`],
              ["Delta best bid", fmtPrice(i.book.bestBid)],
              ["Delta best ask", fmtPrice(i.book.bestAsk)],
              ["Mode", i.risk.mode.replace("_", " ")],
              ...(i.final.note ? ([["Note", i.final.note]] as [string, string][]) : []),
            ]}
          />
        </Section>
      </div>
      <Section title="Risk checks at that moment">
        <ul className="flex flex-wrap gap-1.5">
          {i.risk.gates.map((g) => (
            <li
              key={g.key}
              title={g.detail}
              className={cn(
                "rounded-full px-2.5 py-1 text-[12px]",
                !g.ok || failing.has(g.label)
                  ? "bg-[color-mix(in_srgb,var(--red)_14%,transparent)] text-red"
                  : "bg-[color-mix(in_srgb,var(--green)_14%,transparent)] text-green",
              )}
            >
              {g.label}
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h4 className="pb-1.5 text-[12px] font-semibold text-label-2">{title}</h4>
      {children}
    </section>
  );
}

function Grid({ rows }: { rows: [string, string][] }) {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-label-2">{k}</dt>
          <dd className="num text-right">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function signed(v: number | null) {
  if (v == null) return "-";
  const s = Math.abs(v).toFixed(1);
  return v > 0.05 ? `+${s}` : v < -0.05 ? `−${s}` : s;
}

function capitalise(s: string) {
  return s ? s[0].toUpperCase() + s.slice(1) : s;
}
