"use client";

import { Slider as Base } from "@base-ui/react/slider";

export function Slider({
  value,
  min,
  max,
  step,
  onChange,
  label,
}: {
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  label: string;
}) {
  return (
    <Base.Root value={value} min={min} max={max} step={step} onValueChange={(v) => onChange(v as number)}>
      <Base.Control className="flex h-7 w-full touch-none items-center">
        <Base.Track className="h-1 w-full rounded-full bg-fill-strong">
          <Base.Indicator className="rounded-full bg-blue" />
          <Base.Thumb
            aria-label={label}
            className="size-[26px] rounded-full bg-white shadow-[0_0.5px_4px_rgba(0,0,0,0.12),0_6px_13px_rgba(0,0,0,0.12)] outline-none focus-visible:ring-4 focus-visible:ring-blue/40"
          />
        </Base.Track>
      </Base.Control>
    </Base.Root>
  );
}
