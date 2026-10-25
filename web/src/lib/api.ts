export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

const KEY_STORAGE = "meridian.controlKey";

export function getControlKey(): string {
  try {
    return localStorage.getItem(KEY_STORAGE) ?? "";
  } catch {
    return "";
  }
}

export function setControlKey(value: string) {
  try {
    localStorage.setItem(KEY_STORAGE, value);
  } catch {
    /* storage unavailable: the key lives for this page only */
  }
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-Control-Key": getControlKey(),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `Request failed with status ${res.status}.`;
    try {
      const data = await res.json();
      if (typeof data.detail === "string") detail = data.detail;
      else if (Array.isArray(data.detail)) detail = data.detail.map((d: { msg: string }) => d.msg).join(" ");
    } catch {
      /* body was not JSON */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  history: () => call<{ prices: import("./types").PricePoint[]; pnl: import("./types").PnlPoint[] }>("GET", "/api/history"),
  events: () => call<import("./types").MeridianEvent[]>("GET", "/api/events"),
  decisions: () => call<import("./types").Decision[]>("GET", "/api/decisions?limit=200"),
  control: (action: "start" | "stop" | "kill" | "resume" | "flatten") =>
    call<{ ok: boolean; message: string }>("POST", `/api/control/${action}`),
  params: (patch: Record<string, unknown>) => call<import("./types").Params>("PATCH", "/api/control/params", patch),
  chaos: (name: "stale_ref" | "price_shock" | "drop_feed" | "ledger_drift") =>
    call<{ ok: boolean; message: string }>("POST", `/api/chaos/${name}`),
};
