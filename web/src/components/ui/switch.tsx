"use client";

import { Switch as Base } from "@base-ui/react/switch";

export function Switch({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <Base.Root
      checked={checked}
      onCheckedChange={onChange}
      aria-label={label}
      className="relative inline-flex h-[31px] w-[51px] shrink-0 rounded-full bg-fill-strong p-[2px] transition-colors duration-200 data-[checked]:bg-green"
    >
      <Base.Thumb className="size-[27px] rounded-full bg-white shadow-[0_3px_8px_rgba(0,0,0,0.15),0_3px_1px_rgba(0,0,0,0.06)] transition-transform duration-200 data-[checked]:translate-x-5" />
    </Base.Root>
  );
}
