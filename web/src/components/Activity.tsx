"use client";

import {
  ArrowDownLeft,
  ArrowUpRight,
  CircleAlert,
  CircleCheck,
  FlaskConical,
  OctagonX,
  Radio,
  RefreshCw,
  Shield,
  SlidersHorizontal,
  type LucideIcon,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import type { MeridianEvent } from "@/lib/types";
import { cn, fmtTime } from "@/lib/format";
import { Card } from "./ui/card";

const KIND: Record<string, { icon: LucideIcon; tint: string }> = {
  fill: { icon: ArrowUpRight, tint: "bg-blue" },
  control: { icon: SlidersHorizontal, tint: "bg-label-2" },
  risk: { icon: Shield, tint: "bg-orange" },
  safety: { icon: Shield, tint: "bg-green" },
  reconcile: { icon: RefreshCw, tint: "bg-orange" },
  halt: { icon: OctagonX, tint: "bg-red" },
  error: { icon: CircleAlert, tint: "bg-red" },
  warning: { icon: CircleAlert, tint: "bg-orange" },
  reject: { icon: CircleAlert, tint: "bg-label-3" },
  chaos: { icon: FlaskConical, tint: "bg-[#AF52DE]" },
  feed: { icon: Radio, tint: "bg-teal" },
  exchange: { icon: Radio, tint: "bg-teal" },
  cancel_all: { icon: CircleCheck, tint: "bg-label-2" },
  system: { icon: CircleCheck, tint: "bg-blue" },
};

export function Activity({ events }: { events: MeridianEvent[] }) {
  return (
    <Card title="Activity" aside={`${events.length} events`}>
      <ol className="mt-3 max-h-[460px] overflow-y-auto px-3 pb-3" aria-live="polite">
        <AnimatePresence initial={false}>
          {events.slice(0, 80).map((ev) => {
            const k = KIND[ev.kind] ?? KIND.system;
            const Icon = ev.kind === "fill" && ev.data.side === "sell" ? ArrowDownLeft : k.icon;
            const tint = ev.kind === "fill" ? (ev.data.side === "sell" ? "bg-red" : "bg-green") : k.tint;
            return (
              <motion.li
                key={ev.id}
                layout
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ type: "spring", stiffness: 400, damping: 32 }}
                className="flex gap-3 rounded-2xl px-2 py-2.5"
              >
                <span className={cn("mt-0.5 grid size-7 shrink-0 place-items-center rounded-full text-white", tint)}>
                  <Icon className="size-4" strokeWidth={2.4} aria-hidden="true" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-[14px] leading-snug">{ev.message}</p>
                  <time className="num text-[12px] text-label-2">{fmtTime(ev.ts)}</time>
                </div>
              </motion.li>
            );
          })}
        </AnimatePresence>
        {!events.length && <li className="px-2 py-10 text-center text-[15px] text-label-2">Nothing has happened yet.</li>}
      </ol>
    </Card>
  );
}
