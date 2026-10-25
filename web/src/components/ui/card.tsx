import { cn } from "@/lib/format";

export function Card({
  title,
  aside,
  className,
  children,
}: {
  title?: React.ReactNode;
  aside?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={cn("rounded-[22px] bg-surface shadow-card", className)}>
      {(title || aside) && (
        <header className="flex items-baseline justify-between gap-4 px-5 pt-5">
          {title && <h2 className="font-display text-[17px] font-semibold tracking-[-0.02em]">{title}</h2>}
          {aside && <div className="text-[13px] text-label-2">{aside}</div>}
        </header>
      )}
      {children}
    </section>
  );
}
