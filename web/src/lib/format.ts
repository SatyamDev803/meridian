const usd = new Intl.NumberFormat("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2 });

export const fmtPrice = (v: number | null | undefined) => (v == null ? "-" : usd.format(v));

export const fmtMoney = (v: number | null | undefined, signed = true) => {
  if (v == null) return "-";
  const s = money.format(Math.abs(v));
  if (!signed) return s;
  return v > 0.004 ? `+${s}` : v < -0.004 ? `−${s}` : s;
};

export const fmtBps = (v: number | null | undefined, digits = 1) =>
  v == null ? "-" : `${v.toFixed(digits)} bps`;

export const fmtSigned = (v: number) => (v > 0 ? `+${v}` : v < 0 ? `−${Math.abs(v)}` : "0");

export const fmtAge = (s: number | null | undefined) => {
  if (s == null) return "never";
  if (s < 1) return "just now";
  if (s < 60) return `${Math.round(s)}s ago`;
  return `${Math.round(s / 60)}m ago`;
};

export const fmtDuration = (s: number) => {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  if (h) return `${h}h ${m}m`;
  if (m) return `${m}m ${sec}s`;
  return `${sec}s`;
};

export const fmtTime = (ms: number) =>
  new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export function cn(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}
