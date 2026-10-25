"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { type Theme, useTheme } from "@/lib/theme";
import { cn } from "@/lib/format";

const OPTIONS: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: "system", label: "Match system", icon: Monitor },
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
];

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  return (
    <div role="radiogroup" aria-label="Appearance" className="flex h-9 items-center rounded-full bg-fill p-[3px]">
      {OPTIONS.map(({ value, label, icon: Icon }) => {
        const active = theme === value;
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={label}
            title={label}
            onClick={() => setTheme(value)}
            className={cn(
              "grid h-[30px] w-[34px] place-items-center rounded-full transition-[background-color,color,box-shadow] duration-200",
              active ? "bg-segment text-label shadow-[0_1px_3px_rgba(0,0,0,0.12)]" : "text-label-2 hover:text-label",
            )}
          >
            <Icon className="size-[15px]" strokeWidth={2.2} />
          </button>
        );
      })}
    </div>
  );
}
