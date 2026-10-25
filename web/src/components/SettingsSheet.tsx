"use client";

import { Dialog } from "@base-ui/react/dialog";
import { X } from "lucide-react";
import { useEffect, useState } from "react";
import { api, getControlKey, setControlKey } from "@/lib/api";
import type { Params, State } from "@/lib/types";
import { Button } from "./ui/button";
import { Slider } from "./ui/slider";
import { Switch } from "./ui/switch";
import { ThemeToggle } from "./ThemeToggle";

type Num = "spread_bps" | "skew_bps" | "order_size" | "max_position" | "guard_bps" | "max_session_loss";

const FIELDS: { key: Num; label: string; help: string; min: number; max: number; step: number; unit: string }[] = [
  { key: "spread_bps", label: "Spread", help: "Distance between our bid and ask.", min: 2, max: 60, step: 0.5, unit: "bps" },
  { key: "skew_bps", label: "Inventory lean", help: "How hard quotes lean away from a full inventory.", min: 0, max: 40, step: 0.5, unit: "bps" },
  { key: "order_size", label: "Order size", help: "Contracts on each side. One contract is 0.001 BTC.", min: 1, max: 100, step: 1, unit: "contracts" },
  { key: "max_position", label: "Inventory limit", help: "Beyond this we only quote the side that reduces it.", min: 5, max: 500, step: 5, unit: "contracts" },
  { key: "guard_bps", label: "Price agreement limit", help: "Pull quotes if Binance and Delta disagree by more.", min: 5, max: 100, step: 1, unit: "bps" },
  { key: "max_session_loss", label: "Loss limit", help: "Flatten and halt if the session loses this much.", min: 5, max: 500, step: 5, unit: "USD" },
];

const CHAOS = [
  { name: "stale_ref", title: "Freeze Binance", detail: "Stops the reference feed for 10s. Quotes should disappear." },
  { name: "price_shock", title: "Fake a price shock", detail: "Shifts Binance by 60 bps for 12s. Prices no longer agree." },
  { name: "drop_feed", title: "Drop Delta's socket", detail: "Kills the market connection. Meridian reconnects and resyncs." },
  { name: "ledger_drift", title: "Corrupt the ledger", detail: "Books a fill that never happened. Reconcile repairs it." },
] as const;

export function SettingsSheet({
  open,
  onOpenChange,
  state,
  onSaved,
  notify,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  state: State | null;
  onSaved: (p: Params) => void;
  notify: (msg: string, tone?: "ok" | "error") => void;
}) {
  const [draft, setDraft] = useState<Record<Num, number>>({
    spread_bps: 8, skew_bps: 10, order_size: 10, max_position: 50, guard_bps: 25, max_session_loss: 50,
  });
  const [drift, setDrift] = useState(true);
  const [key, setKey] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open || !state) return;
    const p = state.params;
    setDraft({
      spread_bps: Number(p.spread_bps),
      skew_bps: Number(p.skew_bps),
      order_size: p.order_size,
      max_position: p.max_position,
      guard_bps: Number(p.guard_bps),
      max_session_loss: Number(p.max_session_loss),
    });
    setDrift(p.use_ref_drift);
    setKey(getControlKey());
    // Only reset the form when the sheet opens, not on every live update.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  async function save() {
    setSaving(true);
    try {
      const warn = Math.min(Number(state?.params.warn_bps ?? 10), draft.guard_bps / 2);
      const next = await api.params({ ...draft, warn_bps: warn, use_ref_drift: drift });
      onSaved(next);
      notify("Settings saved. Meridian is using them now.");
      onOpenChange(false);
    } catch (e) {
      notify((e as Error).message, "error");
    } finally {
      setSaving(false);
    }
  }

  async function chaos(name: (typeof CHAOS)[number]["name"]) {
    try {
      const r = await api.chaos(name);
      notify(`Fail-safe test started: ${r.message}.`);
      onOpenChange(false);
    } catch (e) {
      notify((e as Error).message, "error");
    }
  }

  async function flatten() {
    try {
      const r = await api.control("flatten");
      notify(r.message === "already flat" ? "Already flat. Nothing to close." : "Closing the position at market.");
    } catch (e) {
      notify((e as Error).message, "error");
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-40 bg-black/25 backdrop-blur-[2px] transition-opacity duration-300 data-[ending-style]:opacity-0 data-[starting-style]:opacity-0" />
        <Dialog.Popup className="fixed inset-y-2 right-2 z-50 flex w-[min(440px,calc(100vw-16px))] flex-col overflow-hidden rounded-[26px] bg-canvas shadow-2xl transition-transform duration-300 ease-[cubic-bezier(0.32,0.72,0,1)] data-[ending-style]:translate-x-[110%] data-[starting-style]:translate-x-[110%]">
          <div className="flex items-center justify-between px-5 pb-2 pt-5">
            <Dialog.Title className="font-display text-[22px] font-bold tracking-[-0.02em]">Strategy</Dialog.Title>
            <Dialog.Close className="grid size-8 place-items-center rounded-full bg-fill text-label-2 hover:bg-fill-strong" aria-label="Close">
              <X className="size-4" strokeWidth={2.5} />
            </Dialog.Close>
          </div>
          <Dialog.Description className="px-5 text-[13px] text-label-2">
            Changes apply on the next tick, without restarting.
          </Dialog.Description>

          <div className="flex-1 space-y-6 overflow-y-auto px-4 pb-6 pt-4">
            <section className="space-y-1 rounded-2xl bg-surface p-4">
              {FIELDS.map((f) => (
                <div key={f.key} className="pb-3">
                  <div className="flex items-baseline justify-between">
                    <label className="text-[15px]">{f.label}</label>
                    <span className="num text-[15px] font-semibold">
                      {draft[f.key]} <span className="font-normal text-label-2">{f.unit}</span>
                    </span>
                  </div>
                  <Slider
                    label={f.label}
                    value={draft[f.key]}
                    min={f.min}
                    max={f.max}
                    step={f.step}
                    onChange={(v) => setDraft((d) => ({ ...d, [f.key]: v }))}
                  />
                  <p className="text-[12px] text-label-2">{f.help}</p>
                </div>
              ))}
              <div className="flex items-center justify-between gap-4 border-t border-hairline pt-3">
                <div>
                  <div className="text-[15px]">Follow Binance between marks</div>
                  <p className="text-[12px] text-label-2">Adds Binance&apos;s move since Delta&apos;s last mark price.</p>
                </div>
                <Switch checked={drift} onChange={setDrift} label="Follow Binance between marks" />
              </div>
            </section>

            <Button tone="primary" size="lg" className="w-full" onClick={save} disabled={saving}>
              {saving ? "Saving" : "Save settings"}
            </Button>

            {state?.chaosEnabled && (
              <section>
                <h3 className="px-1 pb-2 text-[15px] font-semibold">Test the fail-safes</h3>
                <ul className="divide-y divide-hairline overflow-hidden rounded-2xl bg-surface">
                  {CHAOS.map((c) => (
                    <li key={c.name}>
                      <button
                        type="button"
                        onClick={() => chaos(c.name)}
                        className="w-full px-4 py-3 text-left transition-colors hover:bg-fill"
                      >
                        <div className="text-[15px] text-blue">{c.title}</div>
                        <div className="text-[12px] text-label-2">{c.detail}</div>
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <section>
              <h3 className="px-1 pb-2 text-[15px] font-semibold">Position</h3>
              <div className="rounded-2xl bg-surface p-4">
                <p className="pb-3 text-[13px] text-label-2">
                  Cancels our quotes and closes the whole position with a reduce-only market order.
                </p>
                <Button tone="destructive" className="w-full" onClick={flatten} disabled={!state?.hasKeys}>
                  Close position now
                </Button>
              </div>
            </section>

            <section>
              <h3 className="px-1 pb-2 text-[15px] font-semibold">Appearance</h3>
              <div className="flex items-center justify-between rounded-2xl bg-surface p-4">
                <span className="text-[15px]">Theme</span>
                <ThemeToggle />
              </div>
            </section>

            {state?.controlLocked && (
            <section>
              <h3 className="px-1 pb-2 text-[15px] font-semibold">Access</h3>
              <form className="rounded-2xl bg-surface p-4" onSubmit={(e) => e.preventDefault()}>
                <input type="text" name="username" autoComplete="username" value="meridian" readOnly hidden />
                <label htmlFor="control-key" className="text-[13px] text-label-2">
                  This server is locked. Enter its control key to start, stop or test it.
                </label>
                <input
                  id="control-key"
                  type="password"
                  value={key}
                  onChange={(e) => {
                    setKey(e.target.value);
                    setControlKey(e.target.value);
                  }}
                  className="mt-2 h-10 w-full rounded-xl bg-fill px-3 text-[15px] outline-none focus-visible:ring-2 focus-visible:ring-blue"
                  autoComplete="current-password"
                />
              </form>
            </section>
            )}
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
