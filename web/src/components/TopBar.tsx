"use client";

import { Settings2, Square, Play, OctagonX, RotateCcw } from "lucide-react";
import { Logo } from "./Logo";
import { ThemeToggle } from "./ThemeToggle";
import { Button } from "./ui/button";
import type { Link } from "@/lib/useMeridian";
import type { State } from "@/lib/types";
import { cn } from "@/lib/format";

const STATUS_COPY: Record<State["status"], { text: string; dot: string }> = {
  starting: { text: "Starting", dot: "bg-label-3" },
  idle: { text: "Ready", dot: "bg-label-3" },
  running: { text: "Quoting live", dot: "bg-green" },
  halted: { text: "Halted", dot: "bg-red" },
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
  const status = state ? STATUS_COPY[state.status] : STATUS_COPY.starting;
  const offline = link !== "live";
  const running = state?.status === "running";
  const halted = state?.status === "halted";

  return (
    <header className="sticky top-0 z-30 border-b border-hairline bg-[var(--glass)] backdrop-blur-2xl backdrop-saturate-150">
      <div className="mx-auto flex h-16 max-w-[1440px] items-center gap-4 px-4 sm:px-6">
        <div className="flex items-center gap-2.5">
          <Logo className="size-8" />
          <div className="leading-tight">
            <div className="font-display text-[19px] font-semibold tracking-[-0.025em]">Meridian</div>
            <div className="hidden text-[12px] text-label-2 sm:block">
              {state?.symbol ?? "BTCUSD"} perpetual on Delta testnet
            </div>
          </div>
        </div>

        <div
          className="ml-1 hidden items-center gap-2 rounded-full bg-fill px-3 py-1.5 text-[13px] font-medium md:flex"
          role="status"
          aria-live="polite"
        >
          <span className="relative flex size-2">
            {running && !offline && (
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-green opacity-60" />
            )}
            <span className={cn("relative inline-flex size-2 rounded-full", offline ? "bg-orange" : status.dot)} />
          </span>
          {offline ? (link === "connecting" ? "Connecting to Meridian" : "Meridian is offline") : status.text}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <div className="hidden lg:block">
            <ThemeToggle />
          </div>
          {halted ? (
            <Button tone="tinted" onClick={() => onAction("resume")} disabled={!!busy || offline}>
              <RotateCcw className="size-4" /> Resume
            </Button>
          ) : running ? (
            <Button tone="plain" onClick={() => onAction("stop")} disabled={!!busy || offline}>
              <Square className="size-3.5 fill-current" /> Stop quoting
            </Button>
          ) : (
            <Button
              tone="primary"
              onClick={() => onAction("start")}
              disabled={!!busy || offline || !state?.canTrade}
              title={state?.cannotTradeReason || undefined}
            >
              <Play className="size-3.5 fill-current" /> Start quoting
            </Button>
          )}
          <Button
            tone="destructive"
            onClick={() => onAction("kill")}
            disabled={!!busy || offline || halted}
            aria-label="Kill switch: cancel everything and halt"
          >
            <OctagonX className="size-4" />
            <span className="hidden sm:inline">Kill</span>
          </Button>
          <Button tone="plain" size="icon" onClick={onOpenSettings} aria-label="Strategy settings">
            <Settings2 className="size-[18px]" />
          </Button>
        </div>
      </div>
    </header>
  );
}
