"use client";

import { AnimatePresence, motion } from "motion/react";
import { cn } from "@/lib/format";

export type ToastMsg = { id: number; text: string; tone: "ok" | "error" };

export function Toasts({ items }: { items: ToastMsg[] }) {
  return (
    <div className="pointer-events-none fixed inset-x-0 top-20 z-50 flex flex-col items-center gap-2 px-4" aria-live="assertive">
      <AnimatePresence>
        {items.map((t) => (
          <motion.div
            key={t.id}
            initial={{ opacity: 0, y: -16, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -10, scale: 0.98 }}
            transition={{ type: "spring", stiffness: 420, damping: 30 }}
            className={cn(
              "pointer-events-auto max-w-md rounded-full px-5 py-2.5 text-[14px] font-medium shadow-lg backdrop-blur-xl",
              t.tone === "error" ? "bg-red text-white" : "bg-[color-mix(in_srgb,var(--label)_88%,transparent)] text-[var(--canvas)]",
            )}
          >
            {t.text}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
