"use client";

import { Settings2, OctagonX, RotateCcw } from "lucide-react";
import { Logo } from "./Logo";
import { SectionMenu, SectionNav } from "./SectionNav";
import { Button } from "./ui/button";
import { Switch } from "./ui/switch";
import type { Link } from "@/lib/useMeridian";
import type { State } from "@/lib/types";

const STATUS_COPY: Record<State["status"], string> = {
  starting: "Starting",
  idle: "Quoting off",
  running: "Quoting live",
  halted: "Halted",
};

export function TopBar({
  state,
  link,
  busy,
  onAction,
  onOpenSettings,
}: {
  state: State | null;
  link: Link;
  busy: string | null;
  onAction: (a: "start" | "stop" | "kill" | "resume") => void;
  onOpenSettings: () => void;
}) {
  const offline = link !== "live";
  const running = state?.status === "running";
  const halted = state?.status === "halted";
  const label = offline
    ? link === "connecting"
      ? "Connecting"
      : "Offline"
    : busy === "start"
      ? "Starting"
      : busy === "stop"
        ? "Stopping"
        : STATUS_COPY[state?.status ?? "starting"];

  return (
    <header className="sticky top-0 z-30 border-b border-hairline bg-[var(--glass)] backdrop-blur-2xl backdrop-saturate-150">
      <div className="mx-auto flex h-14 max-w-[1440px] items-center gap-4 px-4 sm:px-6">
        <a href="#overview" aria-label="Meridian, back to top" className="flex shrink-0 items-center gap-2">
          <Logo className="size-7" />
          <span className="hidden font-display text-[18px] font-semibold tracking-[-0.025em] sm:inline">Meridian</span>
        </a>

        <SectionNav className="ml-4 hidden xl:block" />

        <div className="ml-auto flex items-center gap-2 sm:gap-3">
          {halted ? (
            <Button tone="tinted" size="sm" onClick={() => onAction("resume")} disabled={!!busy || offline}>
              <RotateCcw className="size-3.5" /> Resume
            </Button>
          ) : (
            <label
              className="flex items-center gap-2.5"
              title={!running && !state?.canTrade ? state?.cannotTradeReason || undefined : undefined}
            >
              <span role="status" aria-live="polite" className="whitespace-nowrap text-[13px] font-medium sm:text-[14px]">
                {label}
              </span>
              <Switch
                label="Quoting on Delta"
                checked={running}
                disabled={!!busy || offline || (!running && !state?.canTrade)}
                onChange={(on) => onAction(on ? "start" : "stop")}
              />
            </label>
          )}
          <Button
            tone="destructive"
            size="sm"
            onClick={() => onAction("kill")}
            disabled={!!busy || offline || halted}
            aria-label="Kill switch: cancel everything and halt"
          >
            <OctagonX className="size-4" />
            <span className="hidden sm:inline">Kill</span>
          </Button>
          <Button tone="plain" size="icon" onClick={onOpenSettings} aria-label="Settings">
            <Settings2 className="size-[18px]" />
          </Button>
          <SectionMenu className="xl:hidden" />
        </div>
      </div>
    </header>
  );
}
