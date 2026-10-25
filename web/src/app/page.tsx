"use client";

import { useCallback, useRef, useState } from "react";
import { Activity } from "@/components/Activity";
import { DecisionLog } from "@/components/DecisionLog";
import { Economics } from "@/components/Economics";
import { HealthRings } from "@/components/HealthRings";
import { Hero } from "@/components/Hero";
import { Ladder } from "@/components/Ladder";
import { Overview } from "@/components/Overview";
import { PositionCard } from "@/components/PositionCard";
import { SafetyChecks } from "@/components/SafetyChecks";
import { SettingsSheet } from "@/components/SettingsSheet";
import { Toasts, type ToastMsg } from "@/components/Toast";
import { TopBar } from "@/components/TopBar";
import { api } from "@/lib/api";
import { useMeridian } from "@/lib/useMeridian";

const DONE: Record<string, string> = {
  start: "Quoting started.",
  stop: "Quoting stopped. All orders cancelled.",
  kill: "Halted. All orders cancelled.",
  resume: "Resumed. Start quoting when ready.",
};

export default function Dashboard() {
  const { state, events, prices, pnl, link, patchParams, decisions, decisionsAvailable } = useMeridian();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [toasts, setToasts] = useState<ToastMsg[]>([]);
  const nextId = useRef(1);

  const notify = useCallback((text: string, tone: "ok" | "error" = "ok") => {
    const id = nextId.current++;
    setToasts((t) => [...t, { id, text, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3600);
  }, []);

  const act = useCallback(
    async (a: "start" | "stop" | "kill" | "resume") => {
      setBusy(a);
      try {
        await api.control(a);
        notify(DONE[a]);
        // Starting from the hero would otherwise show nothing changing: take the viewer to the live quotes.
        if (a === "start") document.getElementById("market")?.scrollIntoView({ behavior: "smooth" });
      } catch (e) {
        notify((e as Error).message, "error");
      } finally {
        setBusy(null);
      }
    },
    [notify],
  );

  return (
    <>
      <TopBar state={state} link={link} busy={busy} onAction={act} onOpenSettings={() => setSettingsOpen(true)} />
      <Toasts items={toasts} />
      <div className="mx-auto max-w-[1440px] px-4 sm:px-6">
        <Overview state={state} />
      </div>
      <main className="mx-auto grid max-w-[1440px] gap-4 px-4 py-5 sm:px-6 lg:grid-cols-12 lg:gap-5">
        <div className="flex min-w-0 flex-col gap-4 lg:col-span-8 lg:gap-5">
          <div id="market" className="scroll-mt-20">
            <Hero state={state} points={prices} />
          </div>
          <div id="position" className="scroll-mt-20">
            <PositionCard state={state} pnl={pnl} />
          </div>
          <div id="economics" className="scroll-mt-20">
            <Economics state={state} />
          </div>
          <div id="decisions" className="scroll-mt-20">
            <DecisionLog decisions={decisions} available={decisionsAvailable} />
          </div>
          <div id="activity" className="scroll-mt-20">
            <Activity events={events} />
          </div>
        </div>
        <div id="safety" className="flex min-w-0 scroll-mt-20 flex-col gap-4 lg:col-span-4 lg:gap-5">
          <HealthRings state={state} />
          <SafetyChecks state={state} />
          <Ladder state={state} />
        </div>
      </main>
      <footer className="mx-auto max-w-[1440px] px-6 pb-10 pt-2 text-[12px] text-label-2">
        Meridian trades on the Delta Exchange testnet only. Every order is placed by the API, never by hand.
      </footer>
      <SettingsSheet
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
        state={state}
        onSaved={patchParams}
        notify={notify}
      />
    </>
  );
}
