export type Book = "equity" | "etf" | "crypto" | "options";
export type Side = "buy" | "sell";
export type Json = Record<string, any>; // Raw broker/legacy boundary only; normalized contracts below.
// Watchlist capacity is independent of position and exposure limits.
export const MAX_UNIVERSE_SIZE = 40;
export interface Instrument {
  symbol: string;
  book: Book;
  factor: string;
  leverage: number;
  multiplier: number;
  step: number;
  minQty: number;
  tick: number;
  underlying?: string;
  expiry?: string;
  tradable: boolean;
}
export interface Quote {
  bid: number;
  ask: number;
  at: number;
  received: number;
}
export interface Bar {
  t: string;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
  vw?: number;
}
export interface ExitPolicy {
  tp1R: number;
  tp2R: number;
  tp1Fraction: number;
  tp2Fraction: number;
  lockFraction: number;
  trailR: number;
  maxHoldHours: number;
  trailingMode?: "entry_atr" | "realized_vol";
  stagnationMinutes?: number;
  progressR?: number;
  reentry?: boolean;
}
export interface Signal {
  symbol: string;
  book: Book;
  plugin: string;
  at: number;
  expires: number;
  entry: number;
  stop: number;
  score: number;
  reason: string;
  exit: ExitPolicy;
  entryAtr?: number;
  reentryFeature?: Json;
  exitObservation?: { momentum_bps: number; rvol: number };
}
export interface Intent {
  id: string;
  symbol: string;
  campaign: string;
  kind:
    | "entry"
    | "protect"
    | "tp1"
    | "tp2"
    | "stop"
    | "time"
    | "expiry"
    | "stagnation"
    | "signal"
    | "flatten";
  payload: Json;
  at: number;
  status: string;
  order?: Json;
  cancelAt?: number;
  error?: string;
  nativeRole?: "tp1" | "tp2" | "runner" | "stop_leg";
  parentId?: string;
  decisionAt?: number;
  quoteAt?: number;
  ackAt?: number;
  fillObservedAt?: number;
}
export interface ExitPlan {
  id: string;
  kind: Intent["kind"];
  detectedAt: number;
  quoteAt?: number;
  targetSold: number;
  minimumPrice?: number;
  status: "CANCELING" | "READY" | "WORKING" | "COMPLETE";
  orderId?: string;
}
export interface PositionEvaluation {
  campaign: string;
  symbol: string;
  book: Book;
  lastAttempt: number;
  lastCompleted: number;
  outcome: "STARTING" | "EVALUATED" | "STALE_RECONCILIATION" | "OWNERSHIP_UNCERTAIN" | "PENDING_ENTRY" | "NO_INVENTORY" | "STALE_SESSION" | "MARKET_CLOSED" | "STALE_DATA" | "ERROR";
  detail: string;
  quoteAt: number;
  syncAt: number;
}
export interface OrderRetry {
  failures: number;
  lastAt: number;
  nextAt: number;
  lastError: string;
  lastIntent: string;
  requestKey: string;
}
/** Observed partial inventory awaiting cancellation/protection; never order authority. */
export interface PartialEntryRisk {
  source: "BROKER_RECONCILIATION";
  entryId: string;
  firstObservedAt: number;
  lastObservedAt: number;
  deadlineAt: number;
  heldQty: number;
  coveredQty: number;
  cancelRequestedAt: number | null;
  status: "WAIT_CANCEL" | "WAIT_PROTECTION" | "UNVERIFIED" | "RESOLVED";
  overdue: boolean;
  overdueAt?: number;
  resolvedAt?: number;
  resolution?: "CONFIRMED_FLAT" | "CONFIRMED_PROTECTION";
}
export interface Campaign {
  id: string;
  symbol: string;
  book: Book;
  plugin: string;
  created: number;
  instrument: Instrument;
  policy: ExitPolicy;
  risk: number;
  peak: number;
  stop: number;
  closed: boolean;
  intents: string[];
  entryCeiling: number;
  /** Persisted before entry submission; absent/null means unproven legacy attribution. */
  forwardProvenance?: Json | null;
  deadline?: number;
  flatten?: boolean;
  entryAtr?: number;
  dynamicAtr?: number;
  volatility?: Json;
  lastMark?: number;
  stagnationMs?: number;
  closedAt?: number;
  strategyClose?: string;
  astraState?: Json;
  exitPlan?: ExitPlan;
  exitProfile?: string;
  exitRegime?: string;
  nativeDisabledReason?: string;
  protectionChangedAt?: number;
  evaluation?: PositionEvaluation;
  orderRetry?: Partial<Record<"protect" | "urgent" | "profit", OrderRetry>>;
  partialEntryRisk?: PartialEntryRisk;
  protectionTelemetry?: {
    sampledAt: number;
    uncoveredSince: number | null;
    uncoveredTotalMs: number;
    observedPeakPnl: number;
    samples: number;
  };
}
export interface State {
  schema: "HARPOON-XXX-1";
  accountId: string;
  paused: boolean;
  researchPaused: boolean;
  plugins: string[];
  campaigns: Campaign[];
  intents: Intent[];
  peakEquity: number;
  day: string;
  dayEquity: number;
  halt: string;
  events: Json[];
  research: Json;
  sequence: number;
  exitProfile?: "BASELINE_30_1" | "TREND_RUNNER" | "REGIME_ADAPTIVE";
}
export interface Store {
  scan?(prefix: string, limit?: number): Promise<any[]>;
  get(key: string): Promise<any>;
  put(key: string, value: unknown): Promise<unknown>;
  lease(name: string, release?: boolean): Promise<boolean>;
  close(): Promise<void>;
}
export interface Api {
  request(
    path: string,
    method?: string,
    body?: Json,
    market?: boolean,
  ): Promise<any>;
}
export interface Config {
  mode: "paper";
  quant?: { enabled: boolean; calibrationFile?: string; python?: string; timeoutMs?: number; discovery?: boolean; discoveryLimit?: number; config?: Json; microstructure?: Json; optimizer?: Json; accounting?: Json; observations?: Json; operational?: Json };
  execution_authority: "dedicated_remote_account";
  expected_account_id: string;
  stockFeed: "iex" | "sip";
  optionFeed: "opra";
  capitalLimit: number;
  riskFraction: number;
  openRiskFraction: number;
  totalExposure: number;
  assetExposure: number;
  factorExposure: number;
  dailyLoss: number;
  maxDrawdown: number;
  quoteAgeMs: number;
  orderTtlMs: number;
  slippageBps: number;
  cryptoFeeBps: number;
  optionsFeePerContract: number;
  maxSpreadBps: number;
  maxOptionSpreadBps: number;
  maxPositions: number;
  universe: Instrument[];
  optionUnderlyings: string[];
  enabledPlugins: string[];
  exit: ExitPolicy;
  researchMaxRuns: number;
  nativeProtection?: "stop" | "oco" | "oco_trailing";
  protectionRefreshMs?: number;
  streaming?: boolean;
}
export const DEFAULT_EXIT: ExitPolicy = {
  tp1R: 1.5,
  tp2R: 3,
  tp1Fraction: 0.25,
  tp2Fraction: 0.25,
  lockFraction: 0.6,
  trailR: 1.5,
  maxHoldHours: 72,
};
export const TERMINAL = new Set([
  "filled",
  "canceled",
  "expired",
  "rejected",
  "replaced",
]);
export const positive = (v: unknown): v is number =>
  typeof v === "number" && Number.isFinite(v) && v > 0;
export function fresh(
  q: Quote | undefined,
  now: number,
  age = 15000,
): q is Quote {
  return (
    !!q &&
    [q.bid, q.ask, q.at, q.received].every(Number.isFinite) &&
    q.bid > 0 &&
    q.ask >= q.bid &&
    now - q.at >= -2000 &&
    now - q.at <= age &&
    now - q.received >= 0 &&
    now - q.received <= age
  );
}
export function floorStep(n: number, step: number): number {
  if (!positive(step) || !Number.isFinite(n) || n < 0)
    throw Error("Invalid precision/quantity");
  return Number((Math.floor((n + step * 1e-8) / step) * step).toFixed(12));
}
export function price(n: number, tick: number, up = false): string {
  if (!positive(n) || !positive(tick)) throw Error("Invalid price");
  return (
    (up ? Math.ceil((n - 1e-9) / tick) : Math.floor((n + 1e-9) / tick)) * tick
  ).toFixed(Math.max(2, Math.min(9, Math.ceil(-Math.log10(tick)))));
}
export function validateConfig(c: Config): Config {
  if (
    c.nativeProtection !== undefined &&
    !["stop", "oco", "oco_trailing"].includes(c.nativeProtection)
  )
    throw Error("Unsupported native protection mode");
  if (
    c.protectionRefreshMs !== undefined &&
    (!Number.isFinite(c.protectionRefreshMs) ||
      c.protectionRefreshMs < 1000 ||
      c.protectionRefreshMs > 60000)
  )
    throw Error("Invalid protection refresh interval");
  if (c.streaming !== undefined && typeof c.streaming !== "boolean")
    throw Error("Invalid streaming switch");
  if (c.quant !== undefined && typeof c.quant.enabled !== "boolean") throw Error("Invalid quant switch");
  if (c.quant?.discovery !== undefined && typeof c.quant.discovery !== "boolean") throw Error("Invalid discovery switch");
  // Legacy configurations used 48; discovery reports its effective cap of 40.
  if (c.quant?.discoveryLimit !== undefined &&
      (!Number.isInteger(c.quant.discoveryLimit) || c.quant.discoveryLimit < 1 || c.quant.discoveryLimit > 48))
    throw Error("Invalid discovery capacity");
  for (const key of ["requireAccountLedgerForEntries", "requireObservationJournalForEntries"]) {
    const value = c.quant?.operational?.[key];
    if (value !== undefined && typeof value !== "boolean") throw Error("Invalid operational validator switch: " + key);
  }
  const economicGate = c.quant?.operational?.economicGate;
  if (economicGate !== undefined) {
    if (!economicGate || typeof economicGate !== "object" || Array.isArray(economicGate)) throw Error("Economic gate configuration object required");
    for (const key of ["reportFile", "protocolFile", "evidenceFile", "artifactRoot"]) {
      if (typeof economicGate[key] !== "string" || !economicGate[key].trim() || economicGate[key].length > 4096)
        throw Error("Economic gate path required: " + key);
    }
  }
  for (const [key, lo, hi] of [["intervalMs", 30000, 300000], ["maxAgeMs", 30000, 900000],
    ["maxFrames", 2, 100000], ["maxFrameBytes", 1024, 16777216], ["maxSymbolsPerCapture", 1, 48],
    ["maxArchives", 0, 256], ["maxStoredBytes", 1024, 2147483648]] as const) {
    const value = c.quant?.observations?.[key];
    if (value !== undefined && (typeof value !== "number" || !Number.isInteger(value) || value < lo || value > hi))
      throw Error("Observation bounds: " + key);
  }
  const optimizer = c.quant?.optimizer;
  if (optimizer) {
    for (const key of ["enabled", "autoPaper"]) if (optimizer[key] !== undefined && typeof optimizer[key] !== "boolean") throw Error("Invalid optimizer switch");
    for (const [key, lo, hi] of [["lifetimeTrials", 8, 200], ["maxTrials", 3, 32], ["maxGenerations", 1, 8], ["cpuSeconds", .1, 10], ["minGainUsd", 0, 10000], ["minHoldoutTrades", 20, 1000], ["minSortinoPerPeriod", 0, 3]] as const) {
      if (optimizer[key] !== undefined && (typeof optimizer[key] !== "number" || !Number.isFinite(optimizer[key]) || optimizer[key] < lo || optimizer[key] > hi)) throw Error("Optimizer bounds: " + key);
    }
    for (const key of ["lifetimeTrials", "maxTrials", "maxGenerations", "minHoldoutTrades"]) if (optimizer[key] !== undefined && !Number.isInteger(optimizer[key])) throw Error("Integer optimizer budget required");
    for (const key of ["statePath", "panelFile", "performanceFile"]) if (optimizer[key] !== undefined && (typeof optimizer[key] !== "string" || !optimizer[key].length || optimizer[key].length > 4096)) throw Error("Invalid optimizer path");
  }
  const micro = c.quant?.microstructure;
  if (micro) {
    for (const key of ["enabled", "required"]) if (micro[key] !== undefined && typeof micro[key] !== "boolean") throw Error("Invalid microstructure switch: " + key);
    for (const [key, lo, hi] of [
      ["windowSeconds", 10, 300], ["minQuoteEvents", 2, 360], ["minCoverageSeconds", 1, 300],
      ["minWindowCoverageFraction", .01, 1], ["maxQuoteAgeSeconds", .1, 15],
      ["curveMaxSymbols", 2, 48], ["curveEmbargoSeconds", 0, 604800],
    ] as const) {
      const value = micro[key];
      if (value !== undefined && (typeof value !== "number" || !Number.isFinite(value) || value < lo || value > hi)) throw Error("Microstructure bounds: " + key);
    }
    for (const key of ["minQuoteEvents", "curveMaxSymbols"]) if (micro[key] !== undefined && !Number.isInteger(micro[key])) throw Error("Integer microstructure setting required");
    for (const key of ["modelFile", "regimeModelFile", "registryPath"]) if (micro[key] !== undefined && (typeof micro[key] !== "string" || !micro[key].length || micro[key].length > 4096)) throw Error("Invalid microstructure path");
  }
  if (
    c.mode !== "paper" ||
    c.execution_authority !== "dedicated_remote_account" ||
    !c.expected_account_id
  )
    throw Error("Dedicated PAPER account binding required");
  if (!["iex", "sip"].includes(c.stockFeed) || c.optionFeed !== "opra")
    throw Error("Invalid feed; options execution requires OPRA");
  for (const [key, lo, hi] of [
    ["capitalLimit", 100, 1e7],
    ["riskFraction", 0.0001, 0.0025],
    ["openRiskFraction", 0.0001, 0.015],
    ["totalExposure", 0.01, 0.5],
    ["assetExposure", 0.01, 0.25],
    ["factorExposure", 0.01, 0.6],
    ["dailyLoss", 0.001, 0.02],
    ["maxDrawdown", 0.001, 0.08],
    ["quoteAgeMs", 1000, 15000],
    ["orderTtlMs", 5000, 60000],
    ["slippageBps", 1, 50],
    ["cryptoFeeBps", 0, 100],
    ["optionsFeePerContract", 0, 10],
    ["maxSpreadBps", 1, 50],
    ["maxOptionSpreadBps", 1, 1000],
    ["maxPositions", 1, 20],
    ["researchMaxRuns", 0, 100],
  ] as const) {
    const x = c[key];
    if (typeof x !== "number" || !Number.isFinite(x) || x < lo || x > hi)
      throw Error("Config out of bounds: " + key);
  }
  if (
    c.assetExposure > c.totalExposure ||
    c.riskFraction > c.openRiskFraction ||
    !Number.isInteger(c.maxPositions) ||
    !Number.isInteger(c.researchMaxRuns)
  )
    throw Error("Inconsistent risk limits");
  const p = c.exit;
  if (
    !p ||
    ![
      p.tp1R,
      p.tp2R,
      p.tp1Fraction,
      p.tp2Fraction,
      p.lockFraction,
      p.trailR,
      p.maxHoldHours,
    ].every((v) => typeof v === "number" && Number.isFinite(v)) ||
    ![p.tp1R, p.tp2R, p.trailR, p.maxHoldHours].every(positive) ||
    p.tp2R <= p.tp1R ||
    p.maxHoldHours > 72 ||
    p.tp1Fraction <= 0 ||
    p.tp2Fraction < 0 ||
    p.tp1Fraction + p.tp2Fraction > 1 ||
    p.lockFraction < 0.1 ||
    p.lockFraction > 0.9
  )
    throw Error("Invalid exit policy");
  if (
    (p.trailingMode !== undefined &&
      !["entry_atr", "realized_vol"].includes(p.trailingMode)) ||
    (p.stagnationMinutes !== undefined &&
      (!positive(p.stagnationMinutes) || p.stagnationMinutes > 60)) ||
    (p.progressR !== undefined &&
      (!Number.isFinite(p.progressR) || p.progressR < 0 || p.progressR > 2)) ||
    (p.reentry !== undefined && typeof p.reentry !== "boolean")
  )
    throw Error("Invalid optional exit policy");
  if (
    !Array.isArray(c.universe) ||
    !c.universe.length ||
    c.universe.length > MAX_UNIVERSE_SIZE ||
    new Set(c.universe.map((i) => i.symbol)).size !== c.universe.length
  )
    throw Error("Invalid universe");
  for (const i of c.universe) {
    if (
      !["equity", "etf", "crypto"].includes(i.book) ||
      !(
        i.book === "crypto" ? /^[A-Z0-9]+\/USD$/ : /^[A-Z][A-Z0-9.-]{0,9}$/
      ).test(i.symbol) ||
      !i.factor ||
      ![i.leverage, i.multiplier, i.step, i.minQty, i.tick].every(positive) ||
      i.multiplier !== 1 ||
      i.leverage > 3
    )
      throw Error("Invalid instrument " + i.symbol);
  }
  if (
    !Array.isArray(c.optionUnderlyings) ||
    c.optionUnderlyings.length > 8 ||
    c.optionUnderlyings.some(
      (s) => !c.universe.some((i) => i.symbol === s && i.book !== "crypto"),
    )
  )
    throw Error("Option underlyings must be in universe");
  if (
    !Array.isArray(c.enabledPlugins) ||
    new Set(c.enabledPlugins).size !== c.enabledPlugins.length
  )
    throw Error("Invalid plugin selection");
  return structuredClone(c);
}
