"use client";

import { Check, X, Minus } from "lucide-react";
import type { Gate, State } from "@/lib/types";
import { cn, fmtAge } from "@/lib/format";
import { Card } from "./ui/card";

const ACTION_COPY: Record<Gate["action"], string> = {
  widen: "Spread widened",
  reduce: "Reducing only",
  pull: "Quotes pulled",
  halt: "Halted",
};

function Glyph({ gate }: { gate: Gate }) {
  const widened = gate.ok && gate.action === "widen" && gate.detail.includes("widened");
  return (
    <span
      className={cn(
        "grid size-[22px] shrink-0 place-items-center rounded-full text-white",
        !gate.ok ? (gate.action === "reduce" ? "bg-orange" : "bg-red") : widened ? "bg-orange" : "bg-green",
      )}
      aria-hidden="true"
    >
      {!gate.ok ? <X className="size-3.5" strokeWidth={3} /> : widened ? <Minus className="size-3.5" strokeWidth={3} /> : <Check className="size-3.5" strokeWidth={3} />}
    </span>
  );
}

export function SafetyChecks({ state }: { state: State | null }) {
  const gates = state?.risk.gates ?? [];
  const failing = gates.filter((g) => !g.ok);
  const h = state?.health;
  const summary = !gates.length
    ? "Starting checks"
    : failing.length
      ? `${failing.length} of ${gates.length} need attention`
      : `All ${gates.length} passing`;

  return (
    <Card title="Safety checks" aside={summary}>
      <p className="px-5 pt-1 text-[13px] text-label-2">
        Checked four times a second. Quotes rest on Delta only while every check passes.
      </p>
      <ul className="mx-3 mt-3 divide-y divide-hairline overflow-hidden rounded-2xl bg-surface-2">
        {gates.map((g) => (
          <li key={g.key} className="flex items-center gap-3 px-3 py-2.5">
            <Glyph gate={g} />
            <div className="min-w-0 flex-1">
              <div className="text-[15px]">{g.label}</div>
              <div className="num truncate text-[13px] text-label-2">{g.detail}</div>
            </div>
            {!g.ok && (
              <span className={cn("shrink-0 text-[13px] font-medium", g.action === "reduce" ? "text-orange" : "text-red")}>
                {ACTION_COPY[g.action]}
              </span>
            )}
          </li>
        ))}
      </ul>

      <h3 className="px-5 pt-5 text-[15px] font-semibold">Fail-safes</h3>
      <ul className="mx-3 mb-4 mt-2 divide-y divide-hairline overflow-hidden rounded-2xl bg-surface-2 text-[15px]">
        <Row
          ok={h?.deadman.armed ?? false}
          neutral={state?.status !== "running"}
          title="Dead man's switch"
          detail={
            h?.deadman.armed
              ? `Armed. Last heartbeat ${fmtAge(h.deadman.lastAckS)}. Delta cancels our orders if we go quiet for 30s.`
              : "Arms when quoting starts."
          }
        />
        <Row
          ok={h?.reconcile.ok !== false}
          neutral={h?.reconcile.ok == null}
          title="Position reconcile"
          detail={h?.reconcile.detail ?? "Not run yet"}
        />
        <Row
          ok={(h?.rate.used ?? 0) < (h?.rate.limit ?? 1) * 0.95}
          title="Rate budget"
          detail={h ? `${h.rate.used.toLocaleString()} of ${h.rate.limit.toLocaleString()} units, resets in ${Math.round(h.rate.window_resets_in_s)}s` : "-"}
        />
      </ul>
    </Card>
  );
}

function Row({ ok, neutral, title, detail }: { ok: boolean; neutral?: boolean; title: string; detail: string }) {
  return (
    <li className="flex items-center gap-3 px-3 py-2.5">
      <span
        className={cn("size-2.5 shrink-0 rounded-full", neutral ? "bg-label-3" : ok ? "bg-green" : "bg-red")}
        aria-hidden="true"
      />
      <div className="min-w-0">
        <div>{title}</div>
        <div className="text-[13px] text-label-2">{detail}</div>
      </div>
    </li>
  );
}
