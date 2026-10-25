export function Logo({ className }: { className?: string }) {
  // A globe cut by its meridian: the fair price every quote is measured from.
  return (
    <svg viewBox="0 0 28 28" className={className} aria-hidden="true">
      <defs>
        <linearGradient id="mg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#5AC8FA" />
          <stop offset="1" stopColor="#007AFF" />
        </linearGradient>
      </defs>
      <rect width="28" height="28" rx="7" fill="url(#mg)" />
      <ellipse cx="14" cy="14" rx="8.5" ry="8.5" fill="none" stroke="white" strokeOpacity="0.55" strokeWidth="1.4" />
      <ellipse cx="14" cy="14" rx="3.6" ry="8.5" fill="none" stroke="white" strokeOpacity="0.55" strokeWidth="1.4" />
      <line x1="14" y1="3.5" x2="14" y2="24.5" stroke="white" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  );
}
