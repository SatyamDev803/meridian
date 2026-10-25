"use client";

import { Menu, X } from "lucide-react";
import { useEffect, useState } from "react";
import { cn } from "@/lib/format";

const SECTIONS = [
  { id: "overview", label: "Overview" },
  { id: "how", label: "How it works" },
  { id: "market", label: "Market" },
  { id: "position", label: "Position" },
  { id: "economics", label: "Economics" },
  { id: "decisions", label: "Decisions" },
  { id: "safety", label: "Safety" },
];

function useActiveSection() {
  const [active, setActive] = useState("overview");
  useEffect(() => {
    const els = SECTIONS.map((s) => document.getElementById(s.id)).filter((e): e is HTMLElement => !!e);
    // The active section is the last one whose top has passed just under the sticky header.
    const update = () => {
      let current = SECTIONS[0].id;
      for (const el of els) if (el.getBoundingClientRect().top <= 96) current = el.id;
      setActive(current);
    };
    update();
    window.addEventListener("scroll", update, { passive: true });
    return () => window.removeEventListener("scroll", update);
  }, []);
  return active;
}

/** Inline links on wide screens. */
export function SectionNav({ className }: { className?: string }) {
  const active = useActiveSection();
  return (
    <nav aria-label="Sections" className={className}>
      <ul className="flex items-center gap-1">
        {SECTIONS.map((s) => (
          <li key={s.id}>
            <a
              href={`#${s.id}`}
              aria-current={active === s.id ? "location" : undefined}
              className={cn(
                "block whitespace-nowrap rounded-full px-3 py-1.5 text-[14px] transition-colors",
                active === s.id ? "bg-fill font-medium text-label" : "text-label-2 hover:text-label",
              )}
            >
              {s.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/** A menu button and drop-down list for narrow screens. */
export function SectionMenu({ className }: { className?: string }) {
  const active = useActiveSection();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const close = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [open]);

  return (
    <div className={className}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls="section-menu"
        aria-label={open ? "Close sections menu" : "Open sections menu"}
        className="grid size-9 place-items-center rounded-full bg-fill text-label hover:bg-fill-strong"
      >
        {open ? <X className="size-[18px]" /> : <Menu className="size-[18px]" />}
      </button>
      {open && (
        <>
          <button
            type="button"
            aria-hidden="true"
            tabIndex={-1}
            className="fixed inset-0 top-[57px] z-40 cursor-default bg-black/20"
            onClick={() => setOpen(false)}
          />
          <nav
            id="section-menu"
            aria-label="Sections"
            className="absolute inset-x-0 top-full z-50 border-b border-hairline bg-surface px-4 py-2 shadow-card"
          >
            <ul>
              {SECTIONS.map((s) => (
                <li key={s.id}>
                  <a
                    href={`#${s.id}`}
                    onClick={() => setOpen(false)}
                    aria-current={active === s.id ? "location" : undefined}
                    className={cn(
                      "block rounded-xl px-3 py-3 text-[16px]",
                      active === s.id ? "bg-fill font-medium" : "hover:bg-fill",
                    )}
                  >
                    {s.label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
        </>
      )}
    </div>
  );
}
