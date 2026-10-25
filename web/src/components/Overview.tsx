"use client";

import { ArrowDown } from "lucide-react";
import { motion, type Variants } from "motion/react";
import { QuoteSim } from "./QuoteSim";
import type { State } from "@/lib/types";
import { fmtPrice } from "@/lib/format";

const REPO = "https://github.com/SatyamDev803/meridian";

const RISE: Variants = {
  hidden: { opacity: 0, y: 14 },
  show: {
    opacity: 1,
    y: 0,
    transition: { type: "spring", stiffness: 160, damping: 22 },
  },
};

const STEPS = [
  {
    title: "Find fair value",
    body: "Delta's mark price, moved by how far Binance has traded since the last mark. If the two disagree beyond their normal gap, Meridian stops quoting.",
    href: "#market",
    link: "See the live price",
  },
  {
    title: "Quote both sides",
    body: "A post-only bid below fair value and an ask above it, a set spread apart and rounded to Delta's tick. Requoted whenever fair value moves.",
    href: "#market",
    link: "See our quotes",
  },
  {
    title: "Lean against inventory",
    body: "Holding a long position lowers both prices so the sell fills first, and the reverse when short. At the position limit only the reducing side is quoted.",
    href: "#position",
    link: "See the position",
  },
  {
    title: "Check every safety gate",
    body: "Twelve checks, four times a second. A failure widens, pulls, reduces or halts. If the server dies, Delta cancels our orders on its own.",
    href: "#safety",
    link: "See the safety checks",
  },
];

const CRITERIA: { need: string; where: string; href: string }[] = [
  {
    need: "Connect to Delta via API",
    where: "Safety checks: Delta market and account feeds",
    href: "#safety",
  },
  {
    need: "Trade automatically on defined logic",
    where: "Decision log: every order and why",
    href: "#decisions",
  },
  {
    need: "Manage positions and risk",
    where: "Position, health and safety checks",
    href: "#position",
  },
  {
    need: "Show live execution",
    where: "Start quoting, then watch the live market",
    href: "#market",
  },
  {
    need: "Explain the strategy",
    where: "Economics and the README on GitHub",
    href: "#economics",
  },
];

export function Overview({ state }: { state: State | null }) {
  const fair = state?.market?.fair ?? null;
  return (
    <>
      {/* The hero is exactly one screen: viewport height minus the 57px sticky navbar.
        Type scales with the window height so nothing below it peeks into the first view. */}
      <section
        id="overview"
        className="grid min-h-[calc(100svh-57px)] scroll-mt-20 content-center items-center gap-10 py-10 lg:grid-cols-[1.05fr_1fr] lg:gap-14 lg:py-[4vh]"
      >
        <motion.div
          initial="hidden"
          animate="show"
          variants={{ show: { transition: { staggerChildren: 0.09 } } }}
        >
          <motion.p
            variants={RISE}
            className="inline-flex items-center gap-2 text-[15px] font-medium text-blue"
          >
            <span className="relative flex size-2">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-blue opacity-50" />
              <span className="relative inline-flex size-2 rounded-full bg-blue" />
            </span>
            Automated market making on Delta Exchange
          </motion.p>
          <motion.h1
            variants={RISE}
            className="mt-4 max-w-[16ch] bg-linear-to-br from-label via-label to-blue bg-clip-text pb-1 font-display text-[44px] font-semibold leading-[1.02] tracking-[-0.045em] text-transparent sm:text-[64px] lg:text-[clamp(44px,8vh,80px)]"
          >
            A market maker that knows when to stop.
          </motion.h1>
          <motion.p
            variants={RISE}
            className="mt-5 max-w-[56ch] text-[17px] leading-relaxed text-label-2 sm:text-[19px] lg:mt-[2.5vh]"
          >
            Meridian keeps a buy and a sell on the BTCUSD perpetual book at all
            times and earns the gap between them. It leans away from whatever it
            holds, so it drifts back to flat, and it pulls every order the
            moment its data stops making sense.
          </motion.p>
          <motion.div
            variants={RISE}
            className="mt-8 flex flex-wrap items-center gap-3"
          >
            <a
              href="#market"
              className="inline-flex h-11 items-center gap-2 rounded-full bg-blue px-5 text-[16px] font-medium text-white transition hover:brightness-110 active:scale-[0.97]"
            >
              See it trading <ArrowDown className="size-4" aria-hidden="true" />
            </a>
            <a
              href={REPO}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-11 items-center gap-2 rounded-full bg-fill px-5 text-[16px] font-medium transition hover:bg-fill-strong active:scale-[0.97]"
            >
              <GithubMark /> Read the code
            </a>
          </motion.div>
          <motion.p
            variants={RISE}
            className="num mt-5 text-[14px] text-label-2"
          >
            {fair == null
              ? "Connecting to Delta"
              : `BTCUSD fair price ${fmtPrice(fair)}, updated live`}
          </motion.p>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 24, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{
            type: "spring",
            stiffness: 120,
            damping: 20,
            delay: 0.25,
          }}
        >
          <QuoteSim />
        </motion.div>
      </section>

      <section
        id="how"
        className="scroll-mt-20 border-t border-hairline pb-6 pt-14"
      >
        <h2 className="font-display text-[32px] font-semibold tracking-[-0.03em]">
          How it works
        </h2>
        <p className="mt-2 text-[17px] text-label-2">
          Four steps, four times a second.
        </p>
        <ol className="mt-6 grid gap-px overflow-hidden rounded-[22px] bg-hairline shadow-card sm:grid-cols-2 xl:grid-cols-4">
          {STEPS.map((s, i) => (
            <li key={s.title} className="flex flex-col bg-surface p-5">
              <span className="num grid size-8 place-items-center rounded-full bg-[color-mix(in_srgb,var(--blue)_14%,transparent)] text-[15px] font-semibold text-blue">
                {i + 1}
              </span>
              <h3 className="mt-4 font-display text-[17px] font-semibold tracking-[-0.02em]">
                {s.title}
              </h3>
              <p className="mt-1.5 flex-1 text-[14px] leading-relaxed text-label-2">
                {s.body}
              </p>
              <a
                href={s.href}
                className="mt-4 text-[14px] font-medium text-blue hover:underline"
              >
                {s.link}
              </a>
            </li>
          ))}
        </ol>

        <div className="mt-10 grid gap-8 lg:grid-cols-[1fr_1.4fr]">
          <div>
            <h2 className="font-display text-[24px] font-semibold tracking-[-0.025em]">
              What we proved on Delta
            </h2>
            <ul className="mt-4 space-y-3 text-[15px] leading-snug">
              <li>
                <span className="font-semibold">To the cent.</span>{" "}
                <span className="text-label-2">
                  Our ledger matched Delta&apos;s wallet in every test run, fees
                  and tax included.
                </span>
              </li>
              <li>
                <span className="font-semibold">24 seconds.</span>{" "}
                <span className="text-label-2">
                  After we killed the process with kill -9, Delta cancelled our
                  orders by itself.
                </span>
              </li>
              <li>
                <span className="font-semibold">58 real fills.</span>{" "}
                <span className="text-label-2">
                  A spread experiment showing honestly where the money went at
                  each setting.
                </span>
              </li>
            </ul>
          </div>
          <div>
            <h2 className="font-display text-[24px] font-semibold tracking-[-0.025em]">
              Where to look
            </h2>
            <ul className="mt-4 divide-y divide-hairline overflow-hidden rounded-[18px] bg-surface shadow-card">
              {CRITERIA.map((c) => (
                <li key={c.need}>
                  <a
                    href={c.href}
                    className="flex flex-col gap-0.5 px-4 py-3 hover:bg-fill sm:flex-row sm:items-baseline sm:justify-between sm:gap-4"
                  >
                    <span className="text-[15px] font-medium">{c.need}</span>
                    <span className="text-[14px] text-blue sm:text-right">
                      {c.where}
                    </span>
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>
    </>
  );
}

function GithubMark() {
  return (
    <svg
      viewBox="0 0 16 16"
      className="size-4"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  );
}
