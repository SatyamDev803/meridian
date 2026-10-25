export type Status = "starting" | "idle" | "running" | "halted";
export type Mode = "quote" | "reduce_only" | "pull" | "halt";

export interface Gate {
  key: string;
  label: string;
  ok: boolean;
  action: "widen" | "reduce" | "pull" | "halt";
  detail: string;
}

export interface LiveOrder {
  side: "buy" | "sell";
  client_order_id: string;
  order_id: number | null;
  price: string;
  size: number;
  unfilled: number;
  state: string;
}

export interface SocketHealth {
  connected: boolean;
  ready: boolean;
  silence_s: number | null;
  messages: number;
  reconnects: number;
}

export interface Params {
  spread_bps: string;
  skew_bps: string;
  order_size: number;
  max_position: number;
  requote_bps: string;
  guard_bps: string;
  warn_bps: string;
  max_session_loss: string;
  use_ref_drift: boolean;
}

export interface State {
  ts: number;
  status: Status;
  haltReason: string;
  canTrade: boolean;
  cannotTradeReason: string;
  hasKeys: boolean;
  symbol: string;
  chaosEnabled: boolean;
  controlLocked?: boolean;
  contract: { productId: number; tickSize: number; contractValue: number; makerFee: number } | null;
  market: {
    fair: number | null;
    mark: number | null;
    drift: number | null;
    ref: number | null;
    refBid: number | null;
    refAsk: number | null;
    basisBps: number | null;
    disagreementBps: number | null;
    bestBid: number | null;
    bestAsk: number | null;
    spreadBps: number | null;
    band: [number, number] | null;
    book: { bids: [string, string][]; asks: [string, string][] };
    bookSynced: boolean;
    checksumVerified: boolean;
    markAgeS: number | null;
    refAgeS: number | null;
    systemStatus: string;
    tradingStatus: string;
  };
  quotes: {
    bid: number | null;
    bidSize: number;
    ask: number | null;
    askSize: number;
    reservation: number | null;
    halfSpreadBps: number;
    inventoryRatio: number;
    note: string;
    preview: boolean;
  };
  orders: {
    live: { buy: LiveOrder | null; sell: LiveOrder | null };
    in_flight: string[];
    stats: { placed: number; edited: number; cancelled: number; rejected: number };
  } | null;
  position: {
    contracts: number;
    btc: number;
    avgPrice: number | null;
    notionalUsd: number;
    exchangeContracts: number | null;
    max: number;
  };
  pnl: {
    realized: number;
    unrealized: number;
    session: number;
    fees: number;
    fills: number;
    makerRatio: number | null;
    volumeUsd: number;
    maxDrawdown: number;
  };
  risk: { mode: Mode; extraSpreadBps: number; gates: Gate[] };
  params: Params;
  health: {
    public: SocketHealth;
    private: SocketHealth | null;
    binance: SocketHealth;
    rate: { used: number; limit: number; window_resets_in_s: number };
    apiErrors: number;
    deadman: { armed: boolean; lastAckS: number | null };
    reconcile: { at: number | null; ok: boolean | null; detail: string };
  };
  performance: Performance;
  wallet: { balance: number | null; checkedAt: number | null };
  metrics: {
    uptimeS: number;
    runningS: number;
    livelinessPct: number | null;
    requotes: number;
    ticks: number;
  };
}

export interface MeridianEvent {
  id: number;
  ts: number;
  kind: string;
  message: string;
  data: Record<string, unknown>;
}

export interface PricePoint {
  t: number;
  fair: number | null;
  mark: number | null;
  ref: number | null;
  bestBid: number | null;
  bestAsk: number | null;
  bid: number | null;
  ask: number | null;
  live: boolean;
}

export interface PnlPoint {
  t: number;
  realized: number;
  unrealized: number;
  total: number;
  position: number;
}

export interface Performance {
  label: string;
  startedAt: number;
  durationS: number;
  fills: number;
  fillsPerHour: number;
  makerShare: number | null;
  contracts: number;
  edgeAtFillBps: number | null;
  markoutBps: Record<string, number | null>;
  adverseSelectionBps: number | null;
  grossPnl: number;
  fees: number;
  feesEstimated: number;
  feesConfirmed: number;
  netPnl: number;
  exchangePnl: number | null;
  ledgerVsExchange: number | null;
  maxInventory: number;
  maxDrawdown: number;
  quotingPct: number | null;
}

export interface DecisionAction {
  kind: "place" | "edit" | "cancel";
  side: "buy" | "sell";
  price: number | null;
  prevPrice: number | null;
  size: number | null;
  reason: string;
  outcome: string;
}

export interface DecisionInputs {
  capturedAt: number;
  reference: {
    fair: number | null;
    deltaMark: number | null;
    binanceMid: number | null;
    drift: number | null;
    basisBps: number | null;
    disagreementBps: number | null;
  };
  inventory: { position: number; target: number; max: number; ratio: number | null };
  pricing: {
    spreadBps: number | null;
    halfSpreadAppliedBps: number | null;
    skewBps: number | null;
    skewAppliedBps: number | null;
    reservation: number | null;
    disagreementWideningBps: number | null;
    volatilityAdjustmentBps: number | null;
    volatilityModel: string;
    requoteBps: number | null;
  };
  book: { bestBid: number | null; bestAsk: number | null; band: [number, number] | null };
  risk: { mode: Mode; gates: Gate[]; failing: string[] };
  final: { bid: number | null; bidSize: number; ask: number | null; askSize: number; note: string; preview: boolean };
}

export interface Decision {
  id: number;
  ts: number;
  kind: "orders" | "pause" | "resume" | "cancel_all";
  summary: string;
  inputs: DecisionInputs | null;
  actions?: DecisionAction[];
  reasons?: string[];
  mode?: string;
  reason?: string;
}
